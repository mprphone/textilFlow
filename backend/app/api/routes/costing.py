from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import ActualCostEntry, CostLine, CostSheet, Customer, ProductionOrder, Style, User
from ...schemas import (
    ActualCostInput, CostSheetCreate, CostSheetSave, ProposalReleaseRequest,
    WizardProposalCreate,
)
from ...services.audit import record_audit
from ...services.cost_control import list_sheets, order_control, save_sheet, sheet_view
from ...services.costing import rebuild_product_cost, recalculate_sheet
from ...services.cost_sheet_automation import (
    cost_sheet_completeness, ensure_required_cost_lines, refresh_automatic_costs,
)
from ...services.serialization import model_to_dict
from ...services.proposal_wizard import create_from_wizard, wizard_catalog
from ...services.proposal_release import (
    ACCEPTED_STATUSES, ReleaseConflictError, ReleaseValidationError, get_release,
    production_preview, release_sheet_to_production, release_view,
)
from ...services.order_followup import snapshot_approval_needs
from ..deps import current_user, require_module_access, require_role


router = APIRouter(prefix="/costing", tags=["Propostas e custo real"])
WRITE_ROLES = {"admin", "manager", "commercial", "planner"}
ACTUAL_ROLES = {"admin", "manager", "supervisor", "warehouse"}
REOPENABLE_STATUSES = {"rejected", "obsolete"}


def get_sheet(db: Session, sheet_id: int, user: User) -> CostSheet:
    sheet = db.get(CostSheet, sheet_id)
    if not sheet:
        raise HTTPException(404, "Proposta não encontrada")
    require_module_access(db, user, sheet.company_id, {"commercial"})
    return sheet


def _sheet_has_started_production(db: Session, sheet: CostSheet) -> bool:
    meta = dict(sheet.custom_data or {})
    if sheet.status == "production" or any(meta.get(key) for key in (
        "production_order_id", "sales_order_id", "proposal_release_id", "released_at",
    )):
        return True
    for order in db.query(ProductionOrder).filter_by(company_id=sheet.company_id).all():
        if int((order.custom_data or {}).get("approved_cost_sheet_id") or 0) == sheet.id:
            return True
    return False


def _decision_event(action: str, user: User, *, reason: str | None = None) -> dict:
    event = {
        "action": action,
        "at": datetime.now(timezone.utc).isoformat(),
        "user_id": user.id,
        "user_name": user.full_name,
    }
    if reason:
        event["reason"] = reason
    return event


@router.get("/{company_id}/wizard-catalog")
def catalog(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"commercial"})
    return wizard_catalog(db, company_id)


@router.post("/wizard", status_code=201)
def create_wizard_proposal(payload: WizardProposalCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, payload.company_id, WRITE_ROLES)
    if payload.customer_id:
        customer = db.get(Customer, payload.customer_id)
        if not customer or customer.company_id != payload.company_id:
            raise HTTPException(422, "O cliente nao pertence a esta empresa")
    try:
        style, sheet = create_from_wizard(db, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    record_audit(db, company_id=payload.company_id, user_id=user.id, entity="cost-proposal", entity_id=sheet.id, action="create_wizard", payload={"style_id": style.id, "components": len(payload.materials) + len(payload.accessories)})
    db.commit()
    db.refresh(sheet)
    return {"style": model_to_dict(style), **sheet_view(db, sheet)}


@router.get("/{company_id}/sheets")
def sheets(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"commercial"})
    return list_sheets(db, company_id)


@router.post("/sheets", status_code=201)
def create_sheet(payload: CostSheetCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, payload.company_id, WRITE_ROLES)
    style = db.get(Style, payload.style_id)
    if not style or style.company_id != payload.company_id:
        raise HTTPException(404, "Artigo não encontrado")
    customer_id = payload.customer_id or style.customer_id
    customer = None
    if customer_id:
        customer = db.get(Customer, customer_id)
        if not customer or customer.company_id != payload.company_id:
            raise HTTPException(422, "O cliente nao pertence a esta empresa")
    version = (db.query(func.max(CostSheet.version)).filter_by(style_id=style.id).scalar() or 0) + 1
    sheet = CostSheet(
        company_id=payload.company_id, style_id=style.id, version=version, status="draft",
        quantity_basis=payload.quantity, selling_price=payload.selling_price,
        currency=(customer.currency if customer and customer.currency else None),
        custom_data={
            "customer_id": customer_id,
            "quote_no": payload.quote_no,
            "valid_until": (payload.valid_until or (date.today() + timedelta(days=30))).isoformat(),
            "notes": payload.notes,
            "client_notes": payload.client_notes,
            "vat_pct": float(payload.vat_pct or 23),
            "payment_terms": payload.payment_terms or (customer.payment_terms if customer else None) or "30 dias",
            "financial_cost_pct": float(payload.financial_cost_pct),
            "markup_pct": float(payload.markup_pct),
            "commission_pct": float(payload.commission_pct),
            "cost_source": "entered_and_verified",
        },
    )
    db.add(sheet)
    db.flush()
    meta = dict(sheet.custom_data or {})
    meta["quote_no"] = (meta.get("quote_no") or f"PROP-{datetime.now().year}-{sheet.id:05d}").strip()
    sheet.custom_data = meta
    if payload.import_technical_costs:
        rebuild_product_cost(db, sheet)
    else:
        recalculate_sheet(db, sheet)
    ensure_required_cost_lines(db, sheet)
    record_audit(db, company_id=sheet.company_id, user_id=user.id, entity="cost-proposal", entity_id=sheet.id, action="create", payload=payload.model_dump(mode="json"))
    db.commit()
    db.refresh(sheet)
    return sheet_view(db, sheet)


@router.get("/sheets/{sheet_id}")
def detail(sheet_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return sheet_view(db, get_sheet(db, sheet_id, user))


@router.get("/sheets/{sheet_id}/production-preview")
def preview_production(
    sheet_id: int,
    quantity: float | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    sheet = get_sheet(db, sheet_id, user)
    return production_preview(db, sheet, quantity)


@router.post("/sheets/{sheet_id}/autofill")
def autofill_sheet(sheet_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sheet = get_sheet(db, sheet_id, user)
    require_role(db, user, sheet.company_id, WRITE_ROLES)
    if sheet.status != "draft":
        raise HTTPException(409, "Apenas rascunhos podem ser atualizados automaticamente")
    rebuild_product_cost(db, sheet)
    changed = refresh_automatic_costs(db, sheet)
    record_audit(
        db, company_id=sheet.company_id, user_id=user.id, entity="cost-proposal",
        entity_id=sheet.id, action="autofill", payload={"updated_or_added": changed},
    )
    db.commit()
    db.refresh(sheet)
    return sheet_view(db, sheet)


@router.post("/sheets/{sheet_id}/release", status_code=201)
def release_to_production(
    sheet_id: int,
    payload: ProposalReleaseRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    sheet = get_sheet(db, sheet_id, user)
    require_role(db, user, sheet.company_id, {"admin", "manager", "commercial"})
    try:
        release, replayed = release_sheet_to_production(db, sheet.id, payload, user.id)
        if not replayed:
            record_audit(
                db,
                company_id=sheet.company_id,
                user_id=user.id,
                entity="cost-proposal",
                entity_id=sheet.id,
                action="accept_and_release",
                payload={
                    **payload.model_dump(mode="json"),
                    "release_id": release.id,
                    "production_order_id": release.production_order_id,
                },
            )
        db.commit()
        db.refresh(release)
        response.status_code = 200 if replayed else 201
        result = release_view(db, release, already_released=replayed)
        result["proposal"] = sheet_view(db, db.get(CostSheet, sheet.id))
        return result
    except ReleaseValidationError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except ReleaseConflictError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        existing = get_release(db, sheet_id)
        if existing:
            response.status_code = 200
            result = release_view(db, existing, already_released=True)
            result["proposal"] = sheet_view(db, db.get(CostSheet, sheet_id))
            return result
        raise HTTPException(409, "A proposta ou o numero da ordem ja foi lancado") from exc


@router.put("/sheets/{sheet_id}")
def update_sheet(sheet_id: int, payload: CostSheetSave, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sheet = get_sheet(db, sheet_id, user)
    require_role(db, user, sheet.company_id, WRITE_ROLES)
    try:
        save_sheet(db, sheet, payload)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    record_audit(db, company_id=sheet.company_id, user_id=user.id, entity="cost-proposal", entity_id=sheet.id, action="update", payload={"line_count": len(payload.lines)})
    db.commit()
    db.refresh(sheet)
    return sheet_view(db, sheet)


@router.post("/sheets/{sheet_id}/reject")
def reject_sheet(sheet_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sheet = get_sheet(db, sheet_id, user)
    require_role(db, user, sheet.company_id, {"admin", "manager", "commercial"})
    if sheet.status in REOPENABLE_STATUSES:
        return sheet_view(db, sheet)
    if sheet.status not in {"draft", "approved"}:
        raise HTTPException(409, "A proposta já entrou em produção e não pode ser recusada")
    if _sheet_has_started_production(db, sheet):
        raise HTTPException(409, "A proposta já está ligada à produção e não pode ser recusada")
    reason = str(payload.get("reason") or "").strip() or None
    meta = dict(sheet.custom_data or {})
    history = list(meta.get("decision_history") or [])
    event = _decision_event("rejected", user, reason=reason)
    history.append(event)
    meta.update({
        "decision_history": history,
        "rejected_at": event["at"],
        "rejected_by": user.id,
        "rejection_reason": reason,
    })
    sheet.custom_data = meta
    sheet.status = "rejected"
    record_audit(
        db, company_id=sheet.company_id, user_id=user.id, entity="cost-proposal",
        entity_id=sheet.id, action="reject", payload={"reason": reason},
    )
    db.commit()
    db.refresh(sheet)
    return sheet_view(db, sheet)


@router.post("/sheets/{sheet_id}/reopen")
def reopen_sheet(sheet_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sheet = get_sheet(db, sheet_id, user)
    require_role(db, user, sheet.company_id, WRITE_ROLES)
    if sheet.status == "draft":
        return sheet_view(db, sheet)
    if sheet.status not in REOPENABLE_STATUSES:
        raise HTTPException(409, "Apenas propostas recusadas podem ser reabertas para edição")
    if _sheet_has_started_production(db, sheet):
        raise HTTPException(409, "A proposta já está ligada à produção e não pode ser reaberta")
    previous_status = sheet.status
    meta = dict(sheet.custom_data or {})
    history = list(meta.get("decision_history") or [])
    history.append(_decision_event("reopened", user))
    for key in ("approved_at", "approved_by", "accepted_at", "accepted_by", "frozen_lines", "commercial_name"):
        meta.pop(key, None)
    meta["decision_history"] = history
    sheet.custom_data = meta
    sheet.status = "draft"
    ensure_required_cost_lines(db, sheet)
    record_audit(
        db, company_id=sheet.company_id, user_id=user.id, entity="cost-proposal",
        entity_id=sheet.id, action="reopen", payload={"previous_status": previous_status},
    )
    db.commit()
    db.refresh(sheet)
    return sheet_view(db, sheet)


@router.post("/sheets/{sheet_id}/approve")
def approve_sheet(sheet_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sheet = get_sheet(db, sheet_id, user)
    require_role(db, user, sheet.company_id, {"admin", "manager", "commercial"})
    if sheet.status not in {"draft", *REOPENABLE_STATUSES}:
        raise HTTPException(409, "A proposta já não está disponível para aceitação")
    if _sheet_has_started_production(db, sheet):
        raise HTTPException(409, "A proposta já está ligada à produção")
    lines = db.query(CostLine).filter_by(cost_sheet_id=sheet.id).all()
    completeness = cost_sheet_completeness(db, sheet)
    if not completeness["can_accept"]:
        missing = "; ".join(item["label"] for item in completeness["blockers"][:5])
        suffix = "…" if len(completeness["blockers"]) > 5 else ""
        raise HTTPException(422, f"Ficha de custo incompleta: {missing}{suffix}")
    meta = dict(sheet.custom_data or {})
    accepted_at = datetime.now(timezone.utc).isoformat()
    history = list(meta.get("decision_history") or [])
    history.append(_decision_event("accepted", user))
    meta.update({
        "approved_at": accepted_at,
        "approved_by": user.id,
        "accepted_at": accepted_at,
        "accepted_by": user.id,
        "frozen_lines": [model_to_dict(row) for row in lines],
        "commercial_name": user.full_name,
        "decision_history": history,
    })
    sheet.custom_data = meta
    sheet.status = "approved"
    meta["approval_requirements"] = snapshot_approval_needs(db, sheet)
    sheet.custom_data = meta
    record_audit(db, company_id=sheet.company_id, user_id=user.id, entity="cost-proposal", entity_id=sheet.id, action="accept", payload={"total_cost": sheet.total_cost, "selling_price": sheet.selling_price})
    db.commit()
    db.refresh(sheet)
    return sheet_view(db, sheet)


@router.post("/sheets/{sheet_id}/duplicate", status_code=201)
def duplicate_sheet(sheet_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = get_sheet(db, sheet_id, user)
    require_role(db, user, source.company_id, WRITE_ROLES)
    version = (db.query(func.max(CostSheet.version)).filter_by(style_id=source.style_id).scalar() or 0) + 1
    meta = {key: value for key, value in (source.custom_data or {}).items() if key not in {
        "approved_at", "approved_by", "accepted_at", "accepted_by", "frozen_lines",
        "production_order_id", "sales_order_id", "proposal_release_id", "released_at",
        "released_by", "released_quantity",
    }}
    meta["quote_no"] = f"{meta.get('quote_no') or f'PROP-{source.id:05d}'}-R{version}"
    copy = CostSheet(
        company_id=source.company_id, style_id=source.style_id, version=version, status="draft",
        quantity_basis=source.quantity_basis, selling_price=source.selling_price, custom_data=meta,
        currency=source.currency,
    )
    db.add(copy)
    db.flush()
    for line in db.query(CostLine).filter_by(cost_sheet_id=source.id).all():
        db.add(CostLine(
            company_id=copy.company_id, cost_sheet_id=copy.id, category=line.category,
            description=line.description, quantity=line.quantity, unit=line.unit,
            unit_cost=line.unit_cost, amount=line.amount, source_type="revision", source_id=line.id,
        ))
    db.flush()
    recalculate_sheet(db, copy)
    ensure_required_cost_lines(db, copy)
    record_audit(db, company_id=copy.company_id, user_id=user.id, entity="cost-proposal", entity_id=copy.id, action="duplicate", payload={"source_id": source.id})
    db.commit()
    db.refresh(copy)
    return sheet_view(db, copy)


@router.get("/{company_id}/controls")
def controls(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"commercial", "confection", "production"})
    rows = db.query(ProductionOrder).filter_by(company_id=company_id).order_by(ProductionOrder.updated_at.desc()).all()
    result = []
    for row in rows:
        control = order_control(db, row)
        result.append({"order": control["order"], "baseline": control["baseline"], "metrics": control["metrics"]})
    return result


@router.get("/orders/{order_id}/control")
def control_detail(order_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem de fabrico não encontrada")
    require_module_access(db, user, order.company_id, {"commercial", "confection", "production"})
    return order_control(db, order)


@router.post("/orders/{order_id}/actual-costs", status_code=201)
def add_actual_cost(order_id: int, payload: ActualCostInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem de fabrico não encontrada")
    require_role(db, user, order.company_id, ACTUAL_ROLES)
    category = payload.category if payload.category in {"material", "labor", "machine", "subcontract", "overhead", "other"} else "other"
    entry = ActualCostEntry(
        company_id=order.company_id, production_order_id=order.id, category=category,
        description=payload.description.strip(), quantity=payload.quantity, unit=payload.unit.strip(),
        unit_cost=payload.unit_cost, amount=round(payload.quantity * payload.unit_cost, 4),
        occurred_on=payload.occurred_on, reference=payload.reference, notes=payload.notes, user_id=user.id,
    )
    db.add(entry)
    db.flush()
    record_audit(db, company_id=order.company_id, user_id=user.id, entity="actual-cost", entity_id=entry.id, action="create", payload=payload.model_dump(mode="json"))
    db.commit()
    db.refresh(entry)
    return model_to_dict(entry)


@router.post("/orders/{order_id}/baseline/{sheet_id}")
def link_baseline(order_id: int, sheet_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    sheet = get_sheet(db, sheet_id, user)
    if not order or order.company_id != sheet.company_id or order.style_id != sheet.style_id:
        raise HTTPException(422, "A proposta não pertence ao artigo desta ordem")
    require_role(db, user, order.company_id, {"admin", "manager", "planner"})
    if sheet.status not in ACCEPTED_STATUSES:
        raise HTTPException(422, "Apenas propostas aprovadas podem ser usadas como orçamento-base")
    data = dict(order.custom_data or {})
    data["approved_cost_sheet_id"] = sheet.id
    order.custom_data = data
    db.commit()
    return order_control(db, order)
