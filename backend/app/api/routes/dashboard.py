from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import User
from ...services.analytics import dashboard_metrics
from ...services.intelligence import operational_briefing
from ..deps import current_user, require_module_access


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/{company_id}")
def dashboard(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"overview"})
    result = dashboard_metrics(db, company_id)
    result["briefing"] = operational_briefing(db, company_id, result)
    return result
