from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import (
    Customer, CustomerClaim, CustomerReturnLine, FinishedGoodsUnit, Material,
    OperationalAlert, OperationalNotification, ProcurementSuggestion, ProductionOrder,
    ReworkOrder, SalesOrder, Shipment, ShipmentAllocation, ShipmentLine, StyleVariant,
    Supplier, User,
)
from ...services.operations_control import (
    complete_rework, convert_procurement, create_customer_claim,
    dispose_customer_return, dispose_quality_hold, finished_goods_board, reconcile_primavera,
    refresh_procurement_suggestions, scan_code,
)
from ...services.audit import record_audit
from ...services.serialization import model_to_dict
from ..deps import current_user, require_module_access, require_role


router = APIRouter(prefix="/operations-control", tags=["Controlo operacional"])


def _owned(db: Session, model, item_id: int, company_id: int):
    row = db.get(model, item_id)
    if not row or row.company_id != company_id:
        raise HTTPException(404, "Registo não encontrado")
    return row


@router.get("/{company_id}/finished-goods")
def list_finished_goods(company_id: int, limit: int = 250, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"shipping", "production"})
    return finished_goods_board(db, company_id, limit)


@router.get("/{company_id}/rework")
def list_rework(company_id: int, limit: int = 250, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"production"})
    rows = db.query(ReworkOrder).filter_by(company_id=company_id).order_by(ReworkOrder.id.desc()).limit(max(1, min(limit, 1000))).all()
    result = []
    for row in rows:
        order = db.get(ProductionOrder, row.production_order_id)
        variant = db.get(StyleVariant, row.variant_id) if row.variant_id else None
        result.append({
            **model_to_dict(row), "order_no": order.order_no if order else None,
            "variant": " · ".join(value for value in ((variant.color if variant else None), (variant.size if variant else None)) if value),
        })
    return result


@router.get("/{company_id}/quality-holds")
def quality_holds(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"production"})
    rows = db.query(QualityInspection).filter_by(
        company_id=company_id, result="failed", disposition="quarantine"
    ).order_by(QualityInspection.id.desc()).all()
    return [model_to_dict(row) for row in rows]


@router.post("/{company_id}/quality-holds/{item_id}/disposition")
def quality_hold_disposition(company_id: int, item_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "quality", "supervisor"})
    try:
        result = dispose_quality_hold(db, _owned(db, QualityInspection, item_id, company_id), str(payload.get("disposition") or ""), user.id)
        record_audit(db, company_id=company_id, user_id=user.id, entity="quality-inspections", entity_id=item_id, action="disposition", payload=payload)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/rework/{item_id}/complete")
def finish_rework(company_id: int, item_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "quality", "supervisor"})
    try:
        result = complete_rework(db, _owned(db, ReworkOrder, item_id, company_id), payload, user.id)
        record_audit(db, company_id=company_id, user_id=user.id, entity="rework-orders", entity_id=item_id, action="complete", payload=payload)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.get("/{company_id}/claims")
def list_claims(company_id: int, limit: int = 250, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"commercial", "shipping", "production"})
    claims = db.query(CustomerClaim).filter_by(company_id=company_id).order_by(CustomerClaim.id.desc()).limit(max(1, min(limit, 1000))).all()
    result = []
    for row in claims:
        order = db.get(SalesOrder, row.sales_order_id)
        customer = db.get(Customer, row.customer_id)
        shipment = db.get(Shipment, row.shipment_id) if row.shipment_id else None
        result.append({
            **model_to_dict(row), "order_no": order.order_no if order else None,
            "customer": customer.name if customer else None,
            "shipment_no": shipment.shipment_no if shipment else None,
            "lines": [model_to_dict(line) for line in db.query(CustomerReturnLine).filter_by(customer_claim_id=row.id).all()],
        })
    return result


@router.get("/{company_id}/return-options")
def return_options(company_id: int, limit: int = 500, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"commercial", "shipping"})
    rows = db.query(ShipmentAllocation, ShipmentLine, Shipment).join(
        ShipmentLine, ShipmentLine.id == ShipmentAllocation.shipment_line_id
    ).join(Shipment, Shipment.id == ShipmentLine.shipment_id).filter(
        ShipmentAllocation.company_id == company_id
    ).order_by(Shipment.shipped_at.desc()).limit(max(1, min(limit, 1000))).all()
    result = []
    for allocation, line, shipment in rows:
        order = db.get(SalesOrder, shipment.sales_order_id)
        unit = db.get(FinishedGoodsUnit, allocation.finished_goods_unit_id)
        returned = sum(float(item.quantity or 0) for item in db.query(CustomerReturnLine).filter_by(shipment_allocation_id=allocation.id).all())
        available = max(0.0, float(allocation.quantity or 0) - returned)
        if available <= 0.001:
            continue
        result.append({
            "shipment_allocation_id": allocation.id, "shipment_line_id": line.id,
            "sales_order_id": shipment.sales_order_id, "shipment_id": shipment.id,
            "order_no": order.order_no if order else None, "shipment_no": shipment.shipment_no,
            "package_code": unit.package_code if unit else None, "barcode": unit.barcode if unit else None,
            "quantity": available,
        })
    return result


@router.post("/{company_id}/claims", status_code=201)
def add_claim(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "commercial", "warehouse", "quality"})
    try:
        result = create_customer_claim(db, company_id, payload, user.id)
        record_audit(db, company_id=company_id, user_id=user.id, entity="customer-claims", entity_id=result["claim"]["id"], action="create", payload=payload)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/claims/{item_id}/close")
def close_claim(company_id: int, item_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "commercial", "quality"})
    row = _owned(db, CustomerClaim, item_id, company_id)
    row.status = "closed"
    row.resolution = payload.get("resolution")
    row.closed_at = datetime.now(timezone.utc)
    record_audit(db, company_id=company_id, user_id=user.id, entity="customer-claims", entity_id=item_id, action="close", payload=payload)
    db.commit()
    return model_to_dict(row)


@router.post("/{company_id}/returns/{item_id}/disposition")
def return_disposition(company_id: int, item_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "warehouse", "quality"})
    try:
        result = dispose_customer_return(db, _owned(db, CustomerReturnLine, item_id, company_id), str(payload.get("disposition") or ""), user.id)
        record_audit(db, company_id=company_id, user_id=user.id, entity="customer-returns", entity_id=item_id, action="disposition", payload=payload)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.get("/{company_id}/procurement")
def procurement(company_id: int, refresh: bool = True, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"shipping", "erp", "production"})
    rows = refresh_procurement_suggestions(db, company_id) if refresh else db.query(ProcurementSuggestion).filter_by(company_id=company_id).all()
    db.commit()
    result = []
    for row in rows:
        material = db.get(Material, row.material_id)
        supplier = db.get(Supplier, row.supplier_id) if row.supplier_id else None
        order = db.get(ProductionOrder, row.production_order_id) if row.production_order_id else None
        result.append({
            **model_to_dict(row), "material_code": material.code if material else None,
            "material_name": material.name if material else None,
            "supplier": supplier.name if supplier else None,
            "order_no": order.order_no if order else None,
        })
    return result


@router.post("/{company_id}/procurement/convert")
def procurement_convert(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "warehouse"})
    try:
        rows = convert_procurement(db, company_id, [int(value) for value in payload.get("suggestion_ids") or []])
        for row in rows:
            record_audit(db, company_id=company_id, user_id=user.id, entity="purchase-orders", entity_id=row.id, action="auto_create", payload=payload)
        db.commit()
        return [model_to_dict(row) for row in rows]
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.get("/{company_id}/scan/{code:path}")
def scan(company_id: int, code: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"production", "shipping"})
    try:
        return scan_code(db, company_id, code)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


CODE39 = {
    "0":"nnnwwnwnn","1":"wnnwnnnnw","2":"nnwwnnnnw","3":"wnwwnnnnn","4":"nnnwwnnnw",
    "5":"wnnwwnnnn","6":"nnwwwnnnn","7":"nnnwnnwnw","8":"wnnwnnwnn","9":"nnwwnnwnn",
    "A":"wnnnnwnnw","B":"nnwnnwnnw","C":"wnwnnwnnn","D":"nnnnwwnnw","E":"wnnnwwnnn",
    "F":"nnwnwwnnn","G":"nnnnnwwnw","H":"wnnnnwwnn","I":"nnwnnwwnn","J":"nnnnwwwnn",
    "K":"wnnnnnnww","L":"nnwnnnnww","M":"wnwnnnnwn","N":"nnnnwnnww","O":"wnnnwnnwn",
    "P":"nnwnwnnwn","Q":"nnnnnnwww","R":"wnnnnnwwn","S":"nnwnnnwwn","T":"nnnnwnwwn",
    "U":"wwnnnnnnw","V":"nwwnnnnnw","W":"wwwnnnnnn","X":"nwnnwnnnw","Y":"wwnnwnnnn",
    "Z":"nwwnwnnnn","-":"nwnnnnwnw",".":"wwnnnnwnn"," ":"nwwnnnwnn",
    "$":"nwnwnwnnn","/":"nwnwnnnwn","+":"nwnnnwnwn","%":"nnnwnwnwn","*":"nwnnwnwnn",
}


def _barcode_svg(value: str) -> str:
    clean = "".join(char for char in value.upper() if char in CODE39 and char != "*")[:48]
    encoded = f"*{clean}*"
    x, bars = 12, []
    for char in encoded:
        for index, width in enumerate(CODE39[char]):
            size = 3 if width == "w" else 1
            if index % 2 == 0:
                bars.append(f'<rect x="{x}" y="8" width="{size}" height="58"/>')
            x += size
        x += 1
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{x + 12}" height="88" viewBox="0 0 {x + 12} 88"><rect width="100%" height="100%" fill="white"/><g fill="#111">{"".join(bars)}</g><text x="{(x + 12) / 2}" y="80" font-family="sans-serif" font-size="10" text-anchor="middle">{clean}</text></svg>'


@router.get("/{company_id}/labels/{kind}/{item_id}.svg")
def printable_label(company_id: int, kind: str, item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"production", "shipping"})
    model = {"finished-goods": FinishedGoodsUnit, "rework": ReworkOrder}.get(kind)
    if not model:
        raise HTTPException(404, "Tipo de etiqueta inválido")
    row = _owned(db, model, item_id, company_id)
    return Response(_barcode_svg(row.barcode), media_type="image/svg+xml", headers={"Content-Disposition": f'inline; filename="{row.barcode}.svg"'})


@router.get("/{company_id}/notifications")
def notifications(company_id: int, unread_only: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"overview", "production", "shipping"})
    query = db.query(OperationalNotification).filter_by(company_id=company_id, recipient_user_id=user.id)
    if unread_only:
        query = query.filter(OperationalNotification.status != "read")
    result = []
    for row in query.order_by(OperationalNotification.id.desc()).limit(100).all():
        alert = db.get(OperationalAlert, row.operational_alert_id)
        result.append({
            **model_to_dict(row), "title": alert.title if alert else None,
            "detail": alert.detail if alert else None, "severity": alert.severity if alert else None,
            "action_route": alert.action_route if alert else None,
        })
    return result


@router.post("/{company_id}/notifications/{item_id}/read")
def notification_read(company_id: int, item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = _owned(db, OperationalNotification, item_id, company_id)
    if row.recipient_user_id != user.id:
        raise HTTPException(403, "Esta notificação não pertence ao utilizador")
    row.status = "read"
    db.commit()
    return model_to_dict(row)


@router.post("/{company_id}/primavera/reconcile")
def primavera_reconcile(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager"})
    result = reconcile_primavera(db, company_id, payload.get("remote_rows") or [])
    record_audit(db, company_id=company_id, user_id=user.id, entity="primavera-reconciliation", entity_id=0, action="run", payload={"count": len(payload.get("remote_rows") or [])})
    db.commit()
    return result
