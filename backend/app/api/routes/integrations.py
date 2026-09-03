from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Company, User
from ...primavera import PrimaveraConnector
from ...schemas import AssistantQuery, InvoiceQueueIn, PrimaveraConfigIn, SyncMastersIn
from ...services.assistant import answer_factory_question
from ...services.primavera import apply_config, fetch_stock, flush_outbox, PrimaveraError, queue_invoice, test_connection
from ...services.primavera_sync import pull_masters
from ..deps import current_user, require_module_access, require_role


router = APIRouter(tags=["Integrações e assistente"])


def _company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Empresa não encontrada")
    return company


@router.get("/integrations/{company_id}/primavera/status")
def primavera_status(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"management", "erp"})
    return PrimaveraConnector(_company(db, company_id)).status()


@router.put("/integrations/{company_id}/primavera/config")
def primavera_config(company_id: int, payload: PrimaveraConfigIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin"})
    require_module_access(db, user, company_id, {"management", "erp"})
    company = _company(db, company_id)
    status = apply_config(company, payload.model_dump(exclude_unset=True))
    db.commit()
    return status


@router.post("/integrations/{company_id}/primavera/test")
def primavera_test(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin"})
    require_module_access(db, user, company_id, {"management", "erp"})
    company = _company(db, company_id)
    result = test_connection(company)
    db.commit()
    return result


@router.post("/integrations/{company_id}/primavera/flush")
def primavera_flush(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin"})
    require_module_access(db, user, company_id, {"management", "erp"})
    company = _company(db, company_id)
    result = flush_outbox(company, retry_alerts=True)
    db.commit()
    return result


@router.post("/integrations/{company_id}/primavera/invoice")
def primavera_invoice(company_id: int, payload: InvoiceQueueIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager"})
    require_module_access(db, user, company_id, {"management", "erp"})
    company = _company(db, company_id)
    item = queue_invoice(
        company,
        customer_code=payload.customer_code,
        reference=payload.reference,
        lines=payload.lines or [],
    )
    db.commit()
    return item


@router.get("/integrations/{company_id}/primavera/stock")
def primavera_stock(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"shipping", "erp", "management", "warehouse"})
    company = _company(db, company_id)
    try:
        return fetch_stock(company)
    except PrimaveraError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/integrations/{company_id}/primavera/sync")
def primavera_sync(company_id: int, payload: SyncMastersIn | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager"})
    require_module_access(db, user, company_id, {"erp", "management", "shipping", "commercial", "tables", "warehouse"})
    company = _company(db, company_id)
    try:
        result = pull_masters(db, company, (payload.resources if payload else None))
        db.commit()
        return result
    except PrimaveraError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error


@router.post("/assistant/{company_id}/query")
def assistant(company_id: int, payload: AssistantQuery, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"overview"})
    return answer_factory_question(db, company_id, payload.question.strip())
