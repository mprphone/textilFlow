from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import User
from ...services.analytics import cost_overview, employee_performance, machine_performance
from ..deps import current_user, require_module_access


router = APIRouter(prefix="/reports", tags=["Relatórios"])


@router.get("/{company_id}/employees")
def employees(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"overview"})
    return employee_performance(db, company_id)


@router.get("/{company_id}/machines")
def machines(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"overview"})
    return machine_performance(db, company_id)


@router.get("/{company_id}/costs")
def costs(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"overview"})
    return cost_overview(db, company_id)
