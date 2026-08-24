from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import User
from ...services.analytics import cost_overview, downtime_summary, employee_performance, machine_performance
from ...services.operational_reporting import operations_scorecard
from ..deps import current_user, require_module_access


router = APIRouter(prefix="/reports", tags=["Relatórios"])


@router.get("/{company_id}/employees")
def employees(company_id: int, start: date | None = None, end: date | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"overview"})
    return employee_performance(db, company_id, start, end)


@router.get("/{company_id}/machines")
def machines(company_id: int, start: date | None = None, end: date | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"overview"})
    return machine_performance(db, company_id, start, end)


@router.get("/{company_id}/costs")
def costs(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"overview"})
    return cost_overview(db, company_id)


@router.get("/{company_id}/downtime")
def downtime(company_id: int, start: date | None = None, end: date | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"overview"})
    return downtime_summary(db, company_id, start, end)


@router.get("/{company_id}/operations-scorecard")
def operations_report(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"overview", "production", "shipping"})
    return operations_scorecard(db, company_id)
