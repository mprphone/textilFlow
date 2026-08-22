from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth import hash_password, issue_token, verify_password
from ...db import get_db
from ...models import Company, User, UserCompany
from ...schemas import LoginRequest, PasswordChangeRequest
from ...services.modules import company_session
from ..deps import current_user


router = APIRouter(prefix="/auth", tags=["Autenticação"])


def _session_payload(user: User, db: Session, *, token: bool = True) -> dict:
    memberships = db.query(UserCompany, Company).join(Company, Company.id == UserCompany.company_id).filter(
        UserCompany.user_id == user.id, Company.active.is_(True)
    ).all()
    must_change = bool(getattr(user, "must_change_password", False))
    data = {
        "user": {
            "id": user.id, "username": user.username, "name": user.full_name, "email": user.email,
            "must_change_password": must_change,
        },
        "companies": [company_session(company, membership) for membership, company in memberships],
        "must_change_password": must_change,
    }
    if token:
        data["token"] = issue_token(user.id, user.username, must_change=must_change)
    return data


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username, User.active.is_(True)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Credenciais inválidas")
    return _session_payload(user, db)


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    payload = _session_payload(user, db, token=False)
    payload.update({"id": user.id, "username": user.username, "name": user.full_name, "email": user.email})
    return payload


@router.post("/change-password")
def change_password(payload: PasswordChangeRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "Palavra-passe atual incorreta")
    if payload.new_password == "admin123":
        raise HTTPException(400, "Escolha uma palavra-passe diferente da inicial")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    db.commit()
    db.refresh(user)
    return _session_payload(user, db)
