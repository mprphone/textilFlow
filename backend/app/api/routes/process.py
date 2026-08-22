from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Company, ProcessJob, User
from ...schemas import MapMoveInput, MapOrderInput, MapPlanInput
from ...services.cutting_map import add_backlog, move_block, one_click, production_map, unschedule_block
from ...services.modules import enabled_modules
from ...services.process_plant import plant_of, process_cockpit
from ...services.serialization import model_to_dict
from ..deps import current_user, require_module_access

router = APIRouter(prefix="/process", tags=["Processos de fábrica"])


@router.get("/{company_id}/{kind}/cockpit")
def cockpit(company_id: int, kind: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        plant = plant_of(kind)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    require_module_access(db, user, company_id, {plant["id"], "production"})
    company = db.get(Company, company_id)
    if plant["id"] not in enabled_modules(company):
        raise HTTPException(403, f"Esta empresa não tem o módulo {plant['label']} ativo")
    return process_cockpit(db, company_id, kind)


@router.post("/{company_id}/{kind}/jobs", status_code=201)
def create_job(company_id: int, kind: str, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        plant = plant_of(kind)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    require_module_access(db, user, company_id, {plant["id"], "production"})
    company = db.get(Company, company_id)
    if plant["id"] not in enabled_modules(company):
        raise HTTPException(403, f"Esta empresa não tem o módulo {plant['label']} ativo")
    reference = str(payload.get("reference") or "").strip()
    quantity = float(payload.get("quantity") or 0)
    if not reference or quantity <= 0:
        raise HTTPException(422, "Indique a referência e uma quantidade")
    planned = payload.get("planned_date")
    job = ProcessJob(
        company_id=company_id,
        process_kind=plant["kind"],
        production_order_id=payload.get("production_order_id") or None,
        batch_id=payload.get("batch_id") or None,
        line_id=payload.get("line_id") or None,
        machine_id=payload.get("machine_id") or None,
        employee_id=payload.get("employee_id") or None,
        reference=reference,
        quantity=quantity,
        unit=payload.get("unit") or plant["unit"],
        status=payload.get("status") or "planned",
        planned_date=date.fromisoformat(str(planned)[:10]) if planned else None,
        notes=payload.get("notes"),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return model_to_dict(job)


def _require_cutting(db: Session, user: User, company_id: int):
    require_module_access(db, user, company_id, {"corte", "production"})
    company = db.get(Company, company_id)
    if "corte" not in enabled_modules(company):
        raise HTTPException(403, "Esta empresa não tem o módulo Corte ativo")


@router.get("/{company_id}/cutting/map")
def cutting_board(
    company_id: int,
    extra_hours: bool = False,
    weeks: int = Query(default=12, ge=4, le=16),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    _require_cutting(db, user, company_id)
    return production_map(db, company_id, extra_hours, weeks)


@router.post("/{company_id}/cutting/map/move")
def cutting_move(company_id: int, payload: MapMoveInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _require_cutting(db, user, company_id)
    try:
        return move_block(
            db, company_id, payload.plan_id, payload.line_key,
            payload.start_date.isoformat() if payload.start_date else None,
            payload.extra_hours, payload.action,
            payload.from_date.isoformat() if payload.from_date else None,
            payload.supplier_id,
            payload.day_shares,
            payload.fabric_quantity,
            user.id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/cutting/map/unschedule")
def cutting_unschedule(company_id: int, payload: MapPlanInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _require_cutting(db, user, company_id)
    try:
        return unschedule_block(db, company_id, payload.plan_id, payload.extra_hours)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/cutting/map/one-click")
def cutting_one_click(company_id: int, payload: MapPlanInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _require_cutting(db, user, company_id)
    try:
        return one_click(db, company_id, payload.plan_id, payload.extra_hours, payload.fabric_quantity, user.id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/cutting/map/backlog")
def cutting_backlog(company_id: int, payload: MapOrderInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _require_cutting(db, user, company_id)
    try:
        return add_backlog(db, company_id, payload.model_dump(), payload.extra_hours)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
