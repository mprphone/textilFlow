from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Company, User
from ...services.mailbox import (
    MailboxError, delete_account, list_accounts, list_messages, read_message,
    send_email, test_account, upsert_account,
)
from ..deps import current_user, require_module_access, require_role

router = APIRouter(prefix="/mailbox", tags=["Contas de email"])


def _company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Empresa não encontrada")
    return company


def _guard_admin(db: Session, user: User, company_id: int) -> Company:
    require_role(db, user, company_id, {"admin"})
    return _company(db, company_id)


def _guard_use(db: Session, user: User, company_id: int) -> Company:
    require_module_access(db, user, company_id, {"management", "commercial", "overview"})
    return _company(db, company_id)


@router.get("/{company_id}/accounts")
def accounts(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"items": list_accounts(_guard_use(db, user, company_id))}


@router.post("/{company_id}/accounts", status_code=201)
def create_account(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    company = _guard_admin(db, user, company_id)
    try:
        saved = upsert_account(company, payload)
    except MailboxError as error:
        raise HTTPException(422, str(error)) from error
    db.commit()
    return saved


@router.put("/{company_id}/accounts/{account_id}")
def update_account(company_id: int, account_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    company = _guard_admin(db, user, company_id)
    try:
        saved = upsert_account(company, payload, account_id)
    except MailboxError as error:
        raise HTTPException(422, str(error)) from error
    db.commit()
    return saved


@router.delete("/{company_id}/accounts/{account_id}", status_code=204)
def remove_account(company_id: int, account_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    company = _guard_admin(db, user, company_id)
    try:
        delete_account(company, account_id)
    except MailboxError as error:
        raise HTTPException(404, str(error)) from error
    db.commit()


@router.post("/{company_id}/accounts/{account_id}/test")
def test(company_id: int, account_id: int, payload: dict = Body(default={}), db: Session = Depends(get_db), user: User = Depends(current_user)):
    company = _guard_admin(db, user, company_id)
    try:
        result = test_account(company, account_id, str(payload.get("mode") or "both"))
    except MailboxError as error:
        raise HTTPException(422, str(error)) from error
    db.commit()
    return result


@router.post("/{company_id}/accounts/{account_id}/send")
def send(company_id: int, account_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    company = _guard_use(db, user, company_id)
    try:
        return send_email(
            company, account_id,
            to=payload.get("to"), subject=str(payload.get("subject") or ""), body=str(payload.get("body") or ""),
            cc=payload.get("cc"), bcc=payload.get("bcc"), reply_to=payload.get("reply_to"), html=payload.get("html"),
        )
    except MailboxError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/{company_id}/accounts/{account_id}/messages")
def messages(company_id: int, account_id: int, folder: str | None = None, limit: int = 20, unseen: bool = False,
             db: Session = Depends(get_db), user: User = Depends(current_user)):
    company = _guard_use(db, user, company_id)
    try:
        return list_messages(company, account_id, folder=folder, limit=limit, unseen_only=unseen)
    except MailboxError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/{company_id}/accounts/{account_id}/messages/{uid}")
def message(company_id: int, account_id: int, uid: str, folder: str | None = None,
            db: Session = Depends(get_db), user: User = Depends(current_user)):
    company = _guard_use(db, user, company_id)
    try:
        return read_message(company, account_id, uid, folder=folder)
    except MailboxError as error:
        raise HTTPException(422, str(error)) from error
