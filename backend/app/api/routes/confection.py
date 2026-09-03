from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import date
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import User
from ...schemas import (
    CapacityCheckInput, DailyOutputBulkInput, DailyOutputInput, MapMoveInput, MapOrderInput, MapPlanInput,
    MapSimulateInput,
)
from ...services.confection_capacity import capacity_check, confection_overview
from ...services.confection_map import (
    add_backlog, apply_faccao, apply_suggestion, consultant, convert_accept, move_block, one_click,
    production_map, shift_one_day, simulate, toggle_extra, unschedule_block, urgent_insert,
)
from ...services.production import daily_output_options, list_daily_output, record_daily_output, record_daily_output_bulk
from ..deps import current_user, require_module_access


router = APIRouter(prefix="/confection", tags=["Confeção e capacidade"])


@router.get("/{company_id}/overview")
def overview(
    company_id: int,
    weeks: int = Query(default=8, ge=1, le=26),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_module_access(db, user, company_id, {"confection"})
    return confection_overview(db, company_id, weeks)


@router.get("/{company_id}/production-map")
def map_board(
    company_id: int,
    extra_hours: bool = False,
    weeks: int = Query(default=12, ge=4, le=16),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_module_access(db, user, company_id, {"confection"})
    return production_map(db, company_id, extra_hours, weeks)


@router.post("/{company_id}/production-map/move")
def map_move(company_id: int, payload: MapMoveInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"confection"})
    try:
        return move_block(
            db, company_id, payload.plan_id, payload.line_key,
            payload.start_date.isoformat() if payload.start_date else None,
            payload.extra_hours, payload.action,
            payload.from_date.isoformat() if payload.from_date else None,
            payload.supplier_id,
            payload.day_shares,
            payload.fabric_quantity,
            payload.override,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/production-map/unschedule")
def map_unschedule(company_id: int, payload: MapPlanInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"confection"})
    try:
        return unschedule_block(db, company_id, payload.plan_id, payload.extra_hours)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/production-map/one-click")
def map_one_click(company_id: int, payload: MapPlanInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"confection"})
    try:
        return one_click(db, company_id, payload.plan_id, payload.extra_hours, payload.override)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/production-map/shift")
def map_shift(company_id: int, payload: MapPlanInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"confection"})
    return shift_one_day(db, company_id, payload.plan_id, payload.days, payload.extra_hours, payload.override)


@router.post("/{company_id}/production-map/backlog")
def map_backlog(company_id: int, payload: MapOrderInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"confection"})
    return add_backlog(db, company_id, payload.model_dump(), payload.extra_hours)


@router.post("/{company_id}/production-map/urgent")
def map_urgent(company_id: int, payload: MapOrderInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"confection"})
    if not payload.start_date:
        raise HTTPException(422, "Indique o dia de início")
    return urgent_insert(db, company_id, {**payload.model_dump(), "start_date": payload.start_date.isoformat()}, payload.extra_hours)


@router.post("/{company_id}/production-map/extra-hours")
def map_extra(company_id: int, extra_hours: bool = True, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"confection"})
    return toggle_extra(db, company_id, extra_hours)


@router.post("/{company_id}/production-map/consultant")
def map_consultant(company_id: int, extra_hours: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"confection"})
    return consultant(db, company_id, extra_hours)


@router.post("/{company_id}/production-map/apply-suggestion")
def map_apply(company_id: int, code: str, to_line: str, extra_hours: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"confection"})
    try:
        return apply_suggestion(db, company_id, code, to_line, extra_hours)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/production-map/faccao")
def map_faccao(company_id: int, extra_hours: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"confection"})
    try:
        return apply_faccao(db, company_id, extra_hours)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/production-map/simulate")
def map_simulate(company_id: int, payload: MapSimulateInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"confection"})
    if payload.convert:
        return convert_accept(db, company_id, payload.model_dump(), payload.extra_hours)
    return simulate(db, company_id, payload.model_dump(), payload.extra_hours)


@router.post("/capacity-check")
def check_capacity(
    payload: CapacityCheckInput,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_module_access(db, user, payload.company_id, {"confection"})
    try:
        return capacity_check(db, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{company_id}/daily-output")
def daily_output_list(
    company_id: int,
    work_date: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_module_access(db, user, company_id, {"confection", "production"})
    return list_daily_output(db, company_id, work_date or date.today())


@router.get("/{company_id}/daily-output/options")
def daily_output_choices(
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_module_access(db, user, company_id, {"confection", "production"})
    return daily_output_options(db, company_id)


@router.post("/{company_id}/daily-output/bulk")
def daily_output_bulk_create(
    company_id: int,
    payload: DailyOutputBulkInput,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_module_access(db, user, company_id, {"confection", "production"})
    result = record_daily_output_bulk(db, company_id, payload.model_dump())
    db.commit()
    return result


@router.post("/{company_id}/daily-output")
def daily_output_create(
    company_id: int,
    payload: DailyOutputInput,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_module_access(db, user, company_id, {"confection", "production"})
    result = record_daily_output(db, company_id, payload.model_dump())
    db.commit()
    return result
