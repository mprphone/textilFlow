from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import (
    Company, Customer, CuttingJob, Employee, InventoryMovement, Machine, Operation, ProductionBatch,
    ProductionEvent, ProductionLine, ProductionMaterialRequirement, ProductionOrder, ProductionOrderVariant, QualityInspection, StockLot,
    SalesOrder, SalesOrderLine, Sample, Shipment, ShipmentLine, Style, User, WorkAssignment,
)
from ...schemas import ProductionEventRequest, StockMovementRequest
from ...services.analytics import line_performance
from ...services.commercial_docs import from_distribution, public_document
from ...services.inventory import material_history, register_movement, save_material_notes, stock_board
from ...services.primavera import queue_delivery
from ...services.corrections import compensate_event
from ...services.production import register_output
from ...services.production_cockpit import order_cockpit
from ...services.production_split import distribute as distribute_order
from ...services.kanban import complete_sewing_batch, kanban_board, release_batch_to_sewing, request_next_batch
from ...services.production_stage import record_packing, record_revista, update_order_stage
from ...services.shipping import create_partial_shipment, dispatch_status
from ...services.control_tower import control_tower, finite_plan
from ...services.execution import batch_trace, merge_batches, operation_flow, split_batch, transfer_operation
from ...services.serialization import model_to_dict
from ..deps import current_user, require_module_access, require_role


router = APIRouter(prefix="/production", tags=["Produção"])


@router.post("/sales-orders/save")
def save_sales_order(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Grava cabeçalho e grade inteira numa única transação."""
    company_id = int(payload.get("company_id") or 0)
    require_role(db, user, company_id, {"admin", "manager", "commercial", "planner"})
    require_module_access(db, user, company_id, {"commercial"})
    order_id = int(payload.get("id") or 0)
    order = db.get(SalesOrder, order_id) if order_id else None
    if order_id and (not order or order.company_id != company_id):
        raise HTTPException(404, "Encomenda não encontrada")
    if order:
        linked = (
            db.query(ProductionOrder.id)
            .join(SalesOrderLine, SalesOrderLine.id == ProductionOrder.sales_order_line_id)
            .filter(SalesOrderLine.sales_order_id == order.id)
            .first()
        )
        if linked:
            raise HTTPException(409, "A encomenda já foi libertada para produção e a grade está congelada")
    header = payload.get("header") or {}
    status = str(header.get("status") or "confirmed")
    if status not in {"draft", "confirmed"}:
        raise HTTPException(422, "Uma encomenda manual só pode ser gravada como rascunho ou confirmada")
    customer = db.get(Customer, int(header.get("customer_id") or 0))
    if not customer or customer.company_id != company_id:
        raise HTTPException(422, "Escolha um cliente válido")
    order_no = str(header.get("order_no") or "").strip()
    if not order_no:
        raise HTTPException(422, "Indique o número da encomenda")
    items = payload.get("items") or []
    if not items:
        raise HTTPException(422, "Indique pelo menos uma variante com quantidade")
    try:
        if not order:
            order = SalesOrder(company_id=company_id, customer_id=customer.id, order_no=order_no)
            db.add(order)
        order.customer_id = customer.id
        order.order_no = order_no
        order.customer_po = header.get("customer_po")
        order.order_date = date.fromisoformat(header["order_date"]) if header.get("order_date") else None
        order.delivery_date = date.fromisoformat(header["delivery_date"]) if header.get("delivery_date") else None
        order.status = status
        order.currency = str(header.get("currency") or "EUR")[:3].upper()
        order.notes = header.get("notes")
        data = dict(order.custom_data or {})
        data.setdefault("source", "direct_sales_order")
        order.custom_data = data
        db.flush()

        from ...services.inventory import ensure_item_for_variant, ensure_variant
        existing_lines = db.query(SalesOrderLine).filter_by(company_id=company_id, sales_order_id=order.id).all()
        by_variant = {(row.style_id, row.variant_id): row for row in existing_lines}
        used_ids = set()
        seen = set()
        for item in items:
            style = db.get(Style, int(item.get("style_id") or 0))
            quantity = float(item.get("quantity") or 0)
            color = str(item.get("color") or "").strip()
            size = str(item.get("size") or "").strip()
            if not style or style.company_id != company_id or quantity <= 0 or not color or not size:
                raise HTTPException(422, "Artigo, cor, tamanho e quantidade têm de ser válidos")
            key = (style.id, color.casefold(), size.casefold())
            if key in seen:
                raise HTTPException(422, "A grade contém uma variante repetida")
            seen.add(key)
            variant = ensure_variant(db, style, color, size)
            ensure_item_for_variant(db, variant, style)
            line = by_variant.get((style.id, variant.id))
            if not line:
                line = SalesOrderLine(company_id=company_id, sales_order_id=order.id, style_id=style.id, variant_id=variant.id)
                db.add(line)
            line.description = f"{variant.color} · {variant.size}"
            line.quantity = quantity
            line.unit_price = float(item.get("unit_price") or 0)
            line.delivery_date = order.delivery_date
            db.flush()
            used_ids.add(line.id)
        for line in existing_lines:
            if line.id not in used_ids:
                db.delete(line)
        db.commit()
        db.refresh(order)
        saved_lines = db.query(SalesOrderLine).filter_by(sales_order_id=order.id).order_by(SalesOrderLine.id).all()
        return {"order": model_to_dict(order), "lines": [model_to_dict(row) for row in saved_lines]}
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Já existe uma encomenda com esse número") from exc


@router.post("/sales-orders/{order_id}/release")
def release_sales_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Liberta uma encomenda direta para produção de forma repetível e segura."""
    order = db.get(SalesOrder, order_id)
    if not order:
        raise HTTPException(404, "Encomenda não encontrada")
    require_role(db, user, order.company_id, {"admin", "manager", "planner", "commercial"})
    require_module_access(db, user, order.company_id, {"commercial", "production"})
    if order.status in {"cancelled", "partially_shipped", "shipped"}:
        raise HTTPException(409, "O estado atual da encomenda não permite libertação")
    lines = db.query(SalesOrderLine).filter_by(company_id=order.company_id, sales_order_id=order.id).order_by(SalesOrderLine.id).all()
    if not lines:
        raise HTTPException(422, "A encomenda não tem linhas")
    created = []
    reused = []
    try:
        from ...services.cutting_map import ensure_cutting_job_for_order
        from ...services.inventory import ensure_item_for_style
        from ...services.sequences import formatted
        for line in lines:
            production_order = db.query(ProductionOrder).filter_by(
                company_id=order.company_id, sales_order_line_id=line.id
            ).first()
            if production_order:
                reused.append(production_order)
                continue
            style = db.get(Style, line.style_id)
            ensure_item_for_style(db, style)
            number = formatted(db, order.company_id, "production_order", prefix=f"OF-{order.order_no}-", width=3)
            production_order = ProductionOrder(
                company_id=order.company_id, sales_order_line_id=line.id, style_id=line.style_id,
                order_no=number, quantity=float(line.quantity or 0), planned_end=line.delivery_date or order.delivery_date,
                status="planned", priority=3, current_stage="planning",
                custom_data={"source": "direct_sales_order", "sales_order_id": order.id, "variant_id": line.variant_id},
            )
            db.add(production_order)
            db.flush()
            if line.variant_id:
                db.add(ProductionOrderVariant(
                    company_id=order.company_id, production_order_id=production_order.id,
                    variant_id=line.variant_id, quantity=float(line.quantity or 0), unit_price=line.unit_price,
                ))
                db.flush()
            ensure_cutting_job_for_order(db, production_order)
            created.append(production_order)
        order.status = "in_production"
        db.commit()
        return {
            "order": model_to_dict(order),
            "created": [model_to_dict(row) for row in created],
            "existing": [model_to_dict(row) for row in reused],
        }
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Não foi possível numerar as ordens de fabrico") from exc


@router.post("/samples/{sample_id}/release", status_code=201)
def release_sample_to_production(sample_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sample = db.get(Sample, sample_id)
    if not sample:
        raise HTTPException(404, "Amostra não encontrada")
    require_role(db, user, sample.company_id, {"admin", "manager", "planner", "designer"})
    require_module_access(db, user, sample.company_id, {"design"})
    if sample.status != "approved":
        raise HTTPException(409, "A amostra tem de estar aprovada antes de seguir para produção")
    metadata = dict(sample.custom_data or {})
    existing_id = metadata.get("production_order_id")
    if existing_id:
        existing = db.get(ProductionOrder, int(existing_id))
        if existing and existing.company_id == sample.company_id:
            return {"production_order": model_to_dict(existing), "already_released": True}
    order = ProductionOrder(
        company_id=sample.company_id, style_id=sample.style_id, line_id=payload.get("line_id"),
        order_no=str(payload.get("order_no") or "").strip(), quantity=float(payload.get("quantity") or 0),
        planned_start=date.fromisoformat(payload["planned_start"]) if payload.get("planned_start") else None,
        planned_end=date.fromisoformat(payload["planned_end"]) if payload.get("planned_end") else None,
        priority=int(payload.get("priority") or 3), status="planned", current_stage="planning",
        custom_data={"source": "approved_sample", "sample_id": sample.id, "sample_version": sample.version},
    )
    if not order.order_no or order.quantity <= 0:
        raise HTTPException(422, "Indique o número da ordem e uma quantidade válida")
    try:
        db.add(order)
        db.flush()
        style = db.get(Style, sample.style_id)
        from ...services.inventory import ensure_item_for_style
        ensure_item_for_style(db, style)
        from ...services.cutting_map import ensure_cutting_job_for_order
        ensure_cutting_job_for_order(db, order)
        metadata.update({"production_order_id": order.id, "released_to_production_at": datetime.now(timezone.utc).isoformat(), "released_to_production_by": user.id})
        sample.custom_data = metadata
        db.commit()
        db.refresh(order)
        return {"production_order": model_to_dict(order), "already_released": False}
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Já existe uma ordem com esse número") from exc


@router.post("/sales-orders/{order_id}/dispatch", status_code=201)
def dispatch_sales_order(order_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(SalesOrder, order_id)
    if not order:
        raise HTTPException(404, "Encomenda não encontrada")
    require_role(db, user, order.company_id, {"admin", "manager", "warehouse"})
    require_module_access(db, user, order.company_id, {"shipping"})
    checks = [payload.get("quantities_checked"), payload.get("quality_checked"), payload.get("documents_checked"), payload.get("carrier_checked")]
    if not all(checks):
        raise HTTPException(422, "Conclua toda a checklist de expedição")
    try:
        shipment, shipment_lines, status = create_partial_shipment(db, order, {**payload, "user_id": user.id})
        lines = db.query(SalesOrderLine).filter_by(sales_order_id=order.id).all()
        for line in lines:
            for production_order in db.query(ProductionOrder).filter_by(sales_order_line_id=line.id).all():
                update_order_stage(db, production_order)
        erp = None
        company = db.get(Company, order.company_id)
        if company:
            customer = db.get(Customer, order.customer_id)
            quantities = {}
            for shipment_line in shipment_lines:
                quantities[shipment_line.sales_order_line_id] = round(
                    quantities.get(shipment_line.sales_order_line_id, 0) + shipment_line.quantity, 2
                )
            erp = queue_delivery(
                company, order=order, shipment=shipment, customer=customer,
                lines=lines, quantities_by_line=quantities,
            )
        db.commit()
        db.refresh(shipment)
        return {
            "shipment": model_to_dict(shipment),
            "shipment_lines": [model_to_dict(row) for row in shipment_lines],
            "dispatch_status": status,
            "primavera": erp,
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Já existe uma expedição com esse número") from exc


@router.get("/sales-orders/{order_id}/dispatch-status")
def sales_order_dispatch_status(order_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(SalesOrder, order_id)
    if not order:
        raise HTTPException(404, "Encomenda não encontrada")
    require_module_access(db, user, order.company_id, {"shipping", "production", "quality"})
    return dispatch_status(db, order)


@router.get("/{company_id}/shipping-board")
def shipping_board(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"shipping"})
    orders = (
        db.query(SalesOrder)
        .filter_by(company_id=company_id)
        .filter(SalesOrder.status != "cancelled")
        .order_by(SalesOrder.delivery_date.asc(), SalesOrder.id.desc())
        .all()
    )
    shipments = (
        db.query(Shipment)
        .filter_by(company_id=company_id)
        .order_by(Shipment.shipped_at.desc(), Shipment.id.desc())
        .all()
    )
    by_order = {}
    for shipment in shipments:
        by_order.setdefault(shipment.sales_order_id, []).append(model_to_dict(shipment))
    result = []
    for order in orders:
        row = model_to_dict(order)
        row["dispatch"] = dispatch_status(db, order)
        row["shipments"] = by_order.get(order.id, [])
        result.append(row)
    return result


@router.post("/orders/{order_id}/distribute")
def distribute_production_order(order_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem de fabrico não encontrada")
    require_role(db, user, order.company_id, {"admin", "manager", "planner", "supervisor"})
    require_module_access(db, user, order.company_id, {"production", "confection", "subcontracting"})
    try:
        return _distribute_and_document(db, order, {**payload, "user_id": user.id})
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.post("/orders/{order_id}/distribution-document", status_code=201)
def create_distribution_document(order_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem de fabrico não encontrada")
    require_role(db, user, order.company_id, {"admin", "manager", "planner", "supervisor"})
    require_module_access(db, user, order.company_id, {"production", "confection", "subcontracting"})
    document = from_distribution(
        db, order.company_id, order_id=order_id, quantity=float(payload.get("quantity") or 0),
        destination=payload.get("destination"), line_id=payload.get("line_id"),
        subcontract_service_id=payload.get("subcontract_service_id"), subcontract_job_id=payload.get("subcontract_job_id"),
    )
    db.commit()
    db.refresh(document)
    return public_document(db, document)


@router.post("/orders/{order_id}/distribute-and-document", status_code=201)
def distribute_with_document(order_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Distribuir nunca fica só num registo: sai sempre com o documento certo no ERP
    (guia de transporte para serviço externo, guia interna para confeção), para o
    estado da OF ficar sempre rastreável a um documento — nunca só numa gravação silenciosa."""
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem de fabrico não encontrada")
    require_role(db, user, order.company_id, {"admin", "manager", "planner", "supervisor"})
    require_module_access(db, user, order.company_id, {"production", "confection", "subcontracting"})
    try:
        return _distribute_and_document(db, order, {**payload, "user_id": user.id})
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


def _distribute_and_document(db: Session, order: ProductionOrder, payload: dict) -> dict:
    """Confirma movimento e documento na mesma transacao de base de dados."""
    try:
        result = distribute_order(db, order, payload)
        destination = payload.get("destination")
        document = None
        if destination in {"internal", "subcontract", "revista"}:
            document = from_distribution(
                db, order.company_id, order_id=order.id, quantity=float(payload.get("quantity") or 0),
                destination=destination, source=payload.get("source"), line_id=payload.get("line_id"),
                subcontract_service_id=payload.get("subcontract_service_id"),
                subcontract_job_id=result.get("subcontract_job_id"),
            )
        db.commit()
        db.refresh(order)
        if document:
            db.refresh(document)
        result["document"] = public_document(db, document) if document else None
        return result
    except Exception:
        db.rollback()
        raise


@router.post("/orders/{order_id}/revista")
def complete_revista(order_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem de fabrico não encontrada")
    require_role(db, user, order.company_id, {"admin", "manager", "planner", "supervisor", "quality", "operator"})
    require_module_access(db, user, order.company_id, {"quality", "production"})
    try:
        inspection = record_revista(db, order, {**(payload or {}), "user_id": user.id})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    db.refresh(order)
    return {"inspection": model_to_dict(inspection), "current_stage": order.current_stage}


@router.post("/orders/{order_id}/pack")
def pack_production_order(order_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem de fabrico não encontrada")
    require_role(db, user, order.company_id, {"admin", "manager", "planner", "supervisor", "warehouse", "operator"})
    require_module_access(db, user, order.company_id, {"shipping", "production"})
    try:
        result = record_packing(db, order, {**(payload or {}), "user_id": user.id})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return result


@router.post("/events", status_code=201)
def output_event(payload: ProductionEventRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    assignment = db.get(WorkAssignment, payload.assignment_id)
    if not assignment:
        raise HTTPException(404, "Atribuição não encontrada")
    require_module_access(db, user, assignment.company_id, {"production", "confection"})
    event = register_output(db, assignment, payload)
    db.commit()
    db.refresh(event)
    return model_to_dict(event)


@router.post("/events/{event_id}/compensate", status_code=201)
def compensate_output_event(event_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    event = db.get(ProductionEvent, event_id)
    if not event:
        raise HTTPException(404, "Evento não encontrado")
    require_module_access(db, user, event.company_id, {"production", "confection"})
    compensating = compensate_event(db, event_id, str(payload.get("reason") or ""))
    db.commit()
    db.refresh(compensating)
    return model_to_dict(compensating)


@router.get("/{company_id}/stock-board")
def get_stock_board(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"shipping", "production"})
    return stock_board(db, company_id)


@router.get("/{company_id}/materials/{item_key}/history")
def get_material_history(company_id: int, item_key: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"shipping", "production", "commercial"})
    return material_history(db, company_id, item_key)


@router.patch("/{company_id}/materials/{item_key}/notes")
def patch_material_notes(company_id: int, item_key: str, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"commercial", "production", "shipping"})
    material = save_material_notes(db, company_id, item_key, str(payload.get("notes") or ""))
    db.commit()
    db.refresh(material)
    return {"id": material.id, "code": material.code, "notes": material.notes or ""}


@router.get("/{company_id}/next-number")
def get_next_number(company_id: int, key: str, prefix: str = "", width: int = 5, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"commercial", "design", "production"})
    from ...services.sequences import formatted
    number = formatted(db, company_id, key, prefix=prefix, width=width, period=str(date.today().year))
    db.commit()
    return {"number": number}


@router.post("/{company_id}/stock-movements", status_code=201)
def stock_movement(company_id: int, payload: StockMovementRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"production", "shipping"})
    movement = register_movement(db, company_id=company_id, user_id=user.id, payload=payload)
    db.commit()
    db.refresh(movement)
    return model_to_dict(movement)


@router.get("/{company_id}/live")
def live(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"production"})
    active = db.query(WorkAssignment).filter(
        WorkAssignment.company_id == company_id,
        WorkAssignment.status.in_(["queued", "in_progress"]),
    ).all()
    assignments = []
    for row in active:
        employee = db.get(Employee, row.employee_id) if row.employee_id else None
        machine = db.get(Machine, row.machine_id) if row.machine_id else None
        operation = db.get(Operation, row.operation_id)
        order = db.get(ProductionOrder, row.production_order_id)
        style = db.get(Style, order.style_id) if order else None
        batch = db.get(ProductionBatch, row.batch_id) if row.batch_id else None
        assignments.append({
            **model_to_dict(row), "employee": employee.name if employee else "Por atribuir",
            "machine": machine.name if machine else "Manual", "operation": operation.name if operation else "",
            "order_no": order.order_no if order else "", "reference": style.reference if style else "",
            "batch_no": batch.batch_no if batch else "",
            "barcode": (batch.barcode if batch else None) or (order.order_no if order else ""),
            "progress": round(row.completed_quantity / row.planned_quantity * 100, 1) if row.planned_quantity else 0,
            "efficiency": round(row.standard_minutes / row.actual_minutes * 100, 1) if row.actual_minutes else 0,
        })
    return {"lines": line_performance(db, company_id), "assignments": assignments}


@router.get("/orders/{order_id}/trace")
def order_trace(order_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem não encontrada")
    require_module_access(db, user, order.company_id, {"production", "confection", "commercial"})
    return order_cockpit(db, order)


@router.get("/orders/{order_id}/materials")
def order_materials(order_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem nao encontrada")
    require_module_access(db, user, order.company_id, {"production", "confection", "commercial"})
    return [
        model_to_dict(row)
        for row in db.query(ProductionMaterialRequirement)
        .filter_by(production_order_id=order_id)
        .order_by(ProductionMaterialRequirement.id)
        .all()
    ]


@router.post("/orders/{order_id}/alerts/seen")
def mark_alerts_seen(order_id: int, payload: dict = {}, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem nao encontrada")
    require_module_access(db, user, order.company_id, {"production", "confection", "commercial"})
    data = dict(order.custom_data or {})
    alerts = list(data.get("fabric_alerts") or [])
    kinds = set(payload.get("kinds") or [])
    for alert in alerts:
        if not kinds or alert.get("level") in kinds:
            alert["seen"] = True
            alert["seen_at"] = datetime.now(timezone.utc).isoformat()
            alert["seen_by"] = user.id
    data["fabric_alerts"] = alerts
    order.custom_data = data
    db.commit()
    db.refresh(order)
    return {"marked": len(alerts), "custom_data": data}


@router.get("/{company_id}/capacity")
def capacity(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"production"})
    rows = []
    for line in db.query(ProductionLine).filter_by(company_id=company_id, active=True).all():
        work = db.query(WorkAssignment).filter(
            WorkAssignment.line_id == line.id,
            WorkAssignment.status.in_(["queued", "in_progress"]),
        ).all()
        required = sum(max(0, row.standard_minutes - row.actual_minutes) for row in work)
        rows.append({
            "id": line.id, "name": line.name, "mode": line.production_mode,
            "available_minutes": line.capacity_minutes_day, "required_minutes": round(required, 1),
            "load_pct": round(required / line.capacity_minutes_day * 100, 1) if line.capacity_minutes_day else 0,
            "assignments": len(work),
            "wip_limit": line.wip_limit,
            "kanban_pull_enabled": line.kanban_pull_enabled,
        })
    return rows


@router.get("/{company_id}/kanban")
def get_kanban_board(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"production", "confection"})
    return kanban_board(db, company_id)


@router.post("/{company_id}/kanban/pull/{line_id}")
def kanban_pull(company_id: int, line_id: int, payload: dict = {}, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"production", "confection"})
    try:
        batch = request_next_batch(db, company_id, line_id, order_id=payload.get("order_id"))
        if not batch:
            raise HTTPException(404, "Não há lotes cortados à espera")
        db.commit()
        db.refresh(batch)
        return model_to_dict(batch)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/kanban/release/{batch_id}")
def kanban_release(company_id: int, batch_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"production", "confection"})
    line_id = payload.get("line_id")
    if not line_id:
        raise HTTPException(422, "Indique a linha de confeção")
    try:
        batch = release_batch_to_sewing(db, company_id, batch_id, int(line_id))
        db.commit()
        db.refresh(batch)
        return model_to_dict(batch)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/kanban/complete/{batch_id}")
def kanban_complete(company_id: int, batch_id: int, payload: dict = {}, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"production", "confection"})
    try:
        batch = complete_sewing_batch(db, company_id, batch_id, quantity=payload.get("quantity"))
        db.commit()
        db.refresh(batch)
        return model_to_dict(batch)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{company_id}/control-tower")
def get_control_tower(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"production", "confection"})
    try:
        result = control_tower(db, company_id)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post("/{company_id}/finite-plan")
def apply_finite_plan(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "planner", "supervisor"})
    require_module_access(db, user, company_id, {"production", "confection"})
    result = finite_plan(db, company_id, apply=True)
    db.commit()
    return result


@router.get("/orders/{order_id}/operation-flow")
def get_operation_flow(order_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem de fabrico não encontrada")
    require_module_access(db, user, order.company_id, {"production", "confection", "quality"})
    return operation_flow(db, order)


@router.post("/orders/{order_id}/transfer-operation")
def post_operation_transfer(order_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem de fabrico não encontrada")
    require_role(db, user, order.company_id, {"admin", "manager", "planner", "supervisor", "operator"})
    require_module_access(db, user, order.company_id, {"production", "confection"})
    try:
        result = transfer_operation(db, order, payload, user.id)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.post("/batches/{batch_id}/split", status_code=201)
def post_batch_split(batch_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    batch = db.get(ProductionBatch, batch_id)
    if not batch:
        raise HTTPException(404, "Lote não encontrado")
    require_role(db, user, batch.company_id, {"admin", "manager", "planner", "supervisor"})
    require_module_access(db, user, batch.company_id, {"production", "confection"})
    try:
        rows = split_batch(db, batch, payload.get("children") or [], user.id)
        db.commit()
        return [model_to_dict(row) for row in rows]
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/batches/merge", status_code=201)
def post_batch_merge(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "planner", "supervisor"})
    require_module_access(db, user, company_id, {"production", "confection"})
    ids = [int(value) for value in (payload.get("batch_ids") or [])]
    rows = db.query(ProductionBatch).filter(ProductionBatch.id.in_(ids), ProductionBatch.company_id == company_id).all() if ids else []
    if len(rows) != len(set(ids)):
        raise HTTPException(422, "Um ou mais lotes não existem nesta empresa")
    try:
        row = merge_batches(db, rows, payload, user.id)
        db.commit()
        return model_to_dict(row)
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.get("/batches/{batch_id}/trace")
def get_batch_trace(batch_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    batch = db.get(ProductionBatch, batch_id)
    if not batch:
        raise HTTPException(404, "Lote não encontrado")
    require_module_access(db, user, batch.company_id, {"production", "confection", "quality", "shipping"})
    return batch_trace(db, batch)


@router.post("/alerts/{alert_id}/seen")
def see_operational_alert(alert_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ...models import OperationalAlert
    row = db.get(OperationalAlert, alert_id)
    if not row:
        raise HTTPException(404, "Alerta não encontrado")
    require_module_access(db, user, row.company_id, {"production", "confection"})
    row.seen_at = datetime.now(timezone.utc)
    row.seen_by = user.id
    db.commit()
    return model_to_dict(row)


@router.post("/alerts/{alert_id}/resolve")
def resolve_operational_alert(alert_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ...models import OperationalAlert
    row = db.get(OperationalAlert, alert_id)
    if not row:
        raise HTTPException(404, "Alerta não encontrado")
    require_role(db, user, row.company_id, {"admin", "manager", "planner", "supervisor"})
    row.status = "resolved"
    row.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return model_to_dict(row)
