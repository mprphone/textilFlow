from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import User
from ...services.quality import aql_sample_plan
from ..deps import current_user, require_module_access


router = APIRouter(prefix="/quality", tags=["Qualidade"])


@router.get("/{company_id}/aql-plan")
def aql_plan(
    company_id: int, lot_size: float, aql_pct: float = 2.5, inspection_level: str = "II",
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    require_module_access(db, user, company_id, {"production", "shipping", "subcontracting"})
    return aql_sample_plan(lot_size, aql_pct, inspection_level)
