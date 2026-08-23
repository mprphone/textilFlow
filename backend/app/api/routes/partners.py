from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import User
from ...services.supplier_dossier import (
    delete_occurrence, list_order_occurrences, save_profile, supplier_dossier, upsert_occurrence,
)
from ..deps import current_user, require_resource_read, require_resource_write

router = APIRouter(prefix="/partners", tags=["Parceiros"])


@router.get("/{company_id}/suppliers/{supplier_id}/dossier")
def dossier(company_id: int, supplier_id: int, period: str = "12m", date_from: str | None = None,
            date_to: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_resource_read(db, user, company_id, "suppliers")
    return supplier_dossier(db, company_id, supplier_id, period=period, date_from=date_from, date_to=date_to)


@router.patch("/{company_id}/suppliers/{supplier_id}/profile")
def profile(company_id: int, supplier_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_resource_write(db, user, company_id, "suppliers")
    return save_profile(db, company_id, supplier_id, payload)


@router.post("/{company_id}/suppliers/{supplier_id}/occurrences", status_code=201)
def create_occurrence(company_id: int, supplier_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_resource_write(db, user, company_id, "supplier-occurrences")
    return upsert_occurrence(db, company_id, supplier_id, payload)


@router.patch("/{company_id}/suppliers/{supplier_id}/occurrences/{occurrence_id}")
def update_occurrence(company_id: int, supplier_id: int, occurrence_id: int, payload: dict,
                      db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_resource_write(db, user, company_id, "supplier-occurrences")
    return upsert_occurrence(db, company_id, supplier_id, payload, occurrence_id)


@router.delete("/{company_id}/suppliers/{supplier_id}/occurrences/{occurrence_id}", status_code=204)
def remove_occurrence(company_id: int, supplier_id: int, occurrence_id: int,
                      db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_resource_write(db, user, company_id, "supplier-occurrences")
    delete_occurrence(db, company_id, supplier_id, occurrence_id)
    return Response(status_code=204)


@router.get("/{company_id}/orders/{order_id}/occurrences")
def order_occurrences(company_id: int, order_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_resource_read(db, user, company_id, "supplier-occurrences")
    return {"items": list_order_occurrences(db, company_id, order_id)}
