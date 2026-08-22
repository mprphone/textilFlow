from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth import hash_password
from ...db import get_db
from ...models import Company, User, UserCompany
from ...services.company_profile import CompanyProfileError, apply_company_payload, public_company
from ...services.modules import default_enabled_modules, set_enabled_modules
from ..deps import current_user, require_module_access, require_role


router = APIRouter(prefix="/admin", tags=["Administração"])


def public_user(account: User, membership: UserCompany | None = None, memberships: list[UserCompany] | None = None) -> dict:
    data = {
        "id": account.id, "username": account.username, "full_name": account.full_name,
        "email": account.email, "active": account.active,
        "created_at": account.created_at, "updated_at": account.updated_at,
    }
    if membership:
        data.update({"role": membership.role, "permissions": membership.permissions or []})
    rows = memberships if memberships is not None else ([membership] if membership else [])
    data["company_ids"] = [row.company_id for row in rows if row]
    data["memberships"] = [
        {"company_id": row.company_id, "role": row.role, "permissions": row.permissions or []}
        for row in rows if row
    ]
    return data


def _assignable_ids(db: Session, admin: User) -> set[int]:
    return {row.company_id for row in db.query(UserCompany).filter_by(user_id=admin.id).all()}


def _normalized_company_ids(payload: dict, fallback: int, allowed: set[int]) -> list[int]:
    raw = payload.get("company_ids")
    if raw is None:
        ids = [fallback]
    else:
        ids = []
        for item in raw if isinstance(raw, list) else [raw]:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
    unique = []
    for company_id in ids:
        if company_id in allowed and company_id not in unique:
            unique.append(company_id)
    if not unique:
        raise HTTPException(400, "Escolha pelo menos uma empresa a que tenha acesso")
    return unique


def _user_memberships(db: Session, user_id: int) -> list[UserCompany]:
    return db.query(UserCompany).filter_by(user_id=user_id).all()


def _sync_memberships(db: Session, account: User, company_ids: list[int], role: str, permissions: list, actor: User) -> UserCompany | None:
    current = {row.company_id: row for row in _user_memberships(db, account.id)}
    wanted = set(company_ids)
    if account.id == actor.id and not wanted:
        raise HTTPException(400, "Não pode ficar sem empresas")
    for company_id, row in list(current.items()):
        if company_id not in wanted:
            if account.id == actor.id and row.role == "admin":
                continue
            db.delete(row)
            current.pop(company_id, None)
    current_membership = None
    for company_id in company_ids:
        row = current.get(company_id)
        if row is None:
            row = UserCompany(user_id=account.id, company_id=company_id, role=role, permissions=permissions)
            db.add(row)
            current[company_id] = row
        else:
            row.role = role
            row.permissions = permissions
        current_membership = row
    return current_membership


@router.get("/{company_id}/users")
def list_users(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager"})
    require_module_access(db, user, company_id, {"management"})
    rows = db.query(User, UserCompany).join(UserCompany, UserCompany.user_id == User.id).filter(UserCompany.company_id == company_id).all()
    user_ids = [account.id for account, _membership in rows]
    extras = db.query(UserCompany).filter(UserCompany.user_id.in_(user_ids)).all() if user_ids else []
    by_user: dict[int, list[UserCompany]] = {}
    for row in extras:
        by_user.setdefault(row.user_id, []).append(row)
    return [public_user(account, membership, by_user.get(account.id, [membership])) for account, membership in rows]


@router.get("/{company_id}/users/{user_id}")
def get_user(company_id: int, user_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager"})
    require_module_access(db, user, company_id, {"management"})
    account = db.get(User, user_id)
    membership = db.query(UserCompany).filter_by(company_id=company_id, user_id=user_id).first()
    if not account or not membership:
        raise HTTPException(404, "Utilizador não encontrado")
    return public_user(account, membership, _user_memberships(db, user_id))


@router.post("/{company_id}/users", status_code=201)
def create_user(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin"})
    require_module_access(db, user, company_id, {"management"})
    if db.query(User).filter_by(username=payload.get("username")).first():
        raise HTTPException(409, "Nome de utilizador já existe")
    password = str(payload.get("password") or "").strip()
    if len(password) < 6:
        raise HTTPException(400, "A palavra-passe inicial precisa de pelo menos 6 caracteres")
    account = User(
        username=payload["username"], full_name=payload["full_name"], email=payload.get("email"),
        password_hash=hash_password(password),
        must_change_password=True, active=payload.get("active", True) is not False,
    )
    db.add(account)
    db.flush()
    company_ids = _normalized_company_ids(payload, company_id, _assignable_ids(db, user))
    role = payload.get("role", "operator")
    permissions = payload.get("permissions") or []
    membership = _sync_memberships(db, account, company_ids, role, permissions, user)
    db.commit()
    db.refresh(account)
    return public_user(account, membership, _user_memberships(db, account.id))


@router.put("/{company_id}/users/{user_id}")
def update_user_access(company_id: int, user_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin"})
    require_module_access(db, user, company_id, {"management"})
    account = db.get(User, user_id)
    membership = db.query(UserCompany).filter_by(company_id=company_id, user_id=user_id).first()
    if not account or not membership:
        raise HTTPException(404, "Utilizador não encontrado")
    if "full_name" in payload and payload["full_name"]:
        account.full_name = payload["full_name"]
    if "email" in payload:
        account.email = payload.get("email")
    if "active" in payload:
        if user_id == user.id and not bool(payload["active"]):
            raise HTTPException(400, "Não pode inativar a própria conta")
        account.active = bool(payload["active"])
    password = str(payload.get("password") or "").strip()
    if password:
        if len(password) < 6:
            raise HTTPException(400, "A nova palavra-passe precisa de pelo menos 6 caracteres")
        account.password_hash = hash_password(password)
        account.must_change_password = True
    role = payload.get("role", membership.role)
    permissions = payload["permissions"] if "permissions" in payload else (membership.permissions or [])
    if "company_ids" in payload:
        company_ids = _normalized_company_ids(payload, company_id, _assignable_ids(db, user))
        if user_id == user.id and company_id not in company_ids:
            company_ids.append(company_id)
        membership = _sync_memberships(db, account, company_ids, role, permissions, user)
    else:
        membership.role = role
        membership.permissions = permissions
        for row in _user_memberships(db, user_id):
            row.role = role
            row.permissions = permissions
    db.commit()
    db.refresh(account)
    current = db.query(UserCompany).filter_by(company_id=company_id, user_id=user_id).first() or membership
    return public_user(account, current, _user_memberships(db, user_id))


@router.get("/companies")
def companies(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [public_company(company) for company in db.query(Company).join(UserCompany, UserCompany.company_id == Company.id).filter(UserCompany.user_id == user.id).all()]


@router.post("/companies", status_code=201)
def create_company(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    company = Company(
        code=payload["code"], name=payload["name"],
        currency=payload.get("currency", "EUR"), timezone=payload.get("timezone", "Europe/Lisbon"), active=True,
        settings={"enabled_modules": payload.get("enabled_modules") or default_enabled_modules()},
    )
    try:
        apply_company_payload(company, payload, creating=True)
    except CompanyProfileError as error:
        raise HTTPException(400, str(error)) from error
    db.add(company)
    db.flush()
    db.add(UserCompany(user_id=user.id, company_id=company.id, role="admin", permissions=["*"]))
    db.commit()
    db.refresh(company)
    return public_company(company)


@router.put("/companies/{company_id}")
def update_company(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin"})
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Empresa não encontrada")
    try:
        apply_company_payload(company, payload)
    except CompanyProfileError as error:
        raise HTTPException(400, str(error)) from error
    if "enabled_modules" in payload:
        set_enabled_modules(company, payload.get("enabled_modules") or [])
    db.commit()
    db.refresh(company)
    return public_company(company)
