from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import User
from ...services import design as service
from ...services.design_pipeline import DesignError, pipeline_catalog
from ..deps import current_user, require_module_access, require_role

router = APIRouter(prefix="/design", tags=["Desenvolvimento"])
WRITE_ROLES = {"admin", "manager", "designer", "planner"}


def _company(db: Session, user: User, company_id: int, write: bool = False):
    require_module_access(db, user, company_id, {"design"})
    if write:
        require_role(db, user, company_id, WRITE_ROLES)
    return company_id


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DesignError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.get("/{company_id}/pipeline")
def get_pipeline(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id)
    return pipeline_catalog()


@router.get("/{company_id}/team")
def get_team(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id)
    return service.company_team(db, company_id)


@router.get("/{company_id}/today")
def get_today(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id)
    return service.today_dashboard(db, company_id)


@router.get("/{company_id}/organization")
def get_organization(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id)
    return service.organization_board(db, company_id)


@router.get("/{company_id}/report")
def get_report(
    company_id: int,
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    _company(db, user, company_id)
    return service.period_report(db, company_id, start, end)


@router.get("/{company_id}/developments/next-reference")
def get_next_reference(
    company_id: int,
    customer_id: int,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    _company(db, user, company_id)
    user_ids = [user_id] if user_id else []
    return _run(service.next_reference, db, company_id, customer_id, user_ids)


@router.get("/{company_id}/developments")
def list_developments(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id)
    return [service.serialize_development(item) for item in service.list_developments(db, company_id)]


@router.post("/{company_id}/developments", status_code=201)
def post_developments(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    created = _run(service.create_developments, db, company_id, payload)
    return [service.serialize_development(item) for item in created]


@router.get("/{company_id}/developments/{development_id}")
def get_development(company_id: int, development_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id)
    item = _run(service.get_development, db, company_id, development_id)
    return service.serialize_detail(db, item)


@router.post("/{company_id}/developments/{development_id}/move")
def post_move(company_id: int, development_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    item = _run(service.move_development, db, company_id, development_id, payload)
    return service.serialize_development(item)


@router.patch("/{company_id}/developments/{development_id}")
def patch_development(company_id: int, development_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    item = _run(service.patch_development, db, company_id, development_id, payload)
    return service.serialize_development(item)


@router.post("/{company_id}/developments/{development_id}/assignees", status_code=201)
def post_assignee(company_id: int, development_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    item = _run(service.add_assignee, db, company_id, development_id, payload)
    return service.serialize_development(item)


@router.delete("/{company_id}/developments/{development_id}/assignees/{assignee_id}", status_code=204)
def delete_assignee(company_id: int, development_id: int, assignee_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    _run(service.remove_assignee, db, company_id, development_id, assignee_id)


@router.post("/{company_id}/developments/{development_id}/tasks", status_code=201)
def post_task(company_id: int, development_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    item = _run(service.add_task, db, company_id, development_id, payload)
    return service.serialize_development(item)


@router.patch("/{company_id}/developments/{development_id}/tasks/{task_id}")
def patch_task(company_id: int, development_id: int, task_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    item = _run(service.update_task, db, company_id, development_id, task_id, payload)
    return service.serialize_development(item)


@router.delete("/{company_id}/developments/{development_id}/tasks/{task_id}", status_code=204)
def delete_task(company_id: int, development_id: int, task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    _run(service.remove_task, db, company_id, development_id, task_id)


@router.post("/{company_id}/developments/{development_id}/comments", status_code=201)
def post_comment(company_id: int, development_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    author = user.full_name or user.username
    item = _run(service.add_comment, db, company_id, development_id, payload, author)
    return service.serialize_detail(db, item)


@router.put("/{company_id}/developments/{development_id}/stage-notes")
def put_stage_note(company_id: int, development_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    item = _run(service.upsert_stage_note, db, company_id, development_id, payload)
    return service.serialize_detail(db, item)


@router.patch("/{company_id}/developments/{development_id}/stages/{event_id}")
def patch_stage_note(company_id: int, development_id: int, event_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    item = _run(service.update_stage_note, db, company_id, development_id, event_id, payload.get("note"))
    return service.serialize_detail(db, item)


@router.post("/{company_id}/developments/{development_id}/production", status_code=201)
def post_production(company_id: int, development_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    return _run(service.create_production, db, company_id, development_id, payload)


@router.delete("/{company_id}/developments/{development_id}", status_code=204)
def delete_development(company_id: int, development_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _company(db, user, company_id, write=True)
    _run(service.delete_development, db, company_id, development_id)
