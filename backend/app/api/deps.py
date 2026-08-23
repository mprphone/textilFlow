from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..auth import decode_token
from ..db import get_db
from ..models import User, UserCompany


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sessão inválida")
    try:
        user_id = int(decode_token(authorization.split(" ", 1)[1])["sub"])
    except Exception as exc:
        raise HTTPException(401, "Sessão expirada") from exc
    user = db.get(User, user_id)
    if not user or not user.active:
        raise HTTPException(401, "Utilizador inativo")
    return user


def require_company(db: Session, user: User, company_id: int) -> UserCompany:
    membership = db.query(UserCompany).filter_by(user_id=user.id, company_id=company_id).first()
    if not membership:
        raise HTTPException(403, "Sem acesso à empresa")
    return membership


def require_role(db: Session, user: User, company_id: int, roles: set[str]) -> UserCompany:
    membership = require_company(db, user, company_id)
    if membership.role not in roles:
        raise HTTPException(403, "Permissão insuficiente")
    return membership


RESOURCE_WRITE_ROLES = {
    "styles": {"admin", "manager", "designer"},
    "style-variants": {"admin", "manager", "designer"},
    "bom-items": {"admin", "manager", "designer"},
    "product-operations": {"admin", "manager", "designer", "planner"},
    "samples": {"admin", "manager", "designer", "planner"},
    "cost-sheets": {"admin", "manager", "commercial"},
    "cost-lines": {"admin", "manager", "commercial"},
    "exchange-rates": {"admin", "manager", "commercial"},
    "customers": {"admin", "manager", "commercial"},
    "banks": {"admin", "manager", "commercial"},
    "suppliers": {"admin", "manager", "commercial", "warehouse", "planner"},
    "supplier-occurrences": {"admin", "manager", "commercial", "planner", "supervisor", "quality"},
    "skill-types": {"admin", "manager", "planner", "supervisor"},
    "machine-types": {"admin", "manager", "planner", "supervisor"},
    "production-lines": {"admin", "manager", "planner", "supervisor"},
    "warehouses": {"admin", "manager", "warehouse"},
    "payment-terms": {"admin", "manager", "commercial"},
    "materials": {"admin", "manager", "designer", "warehouse", "commercial"},
    "quality-inspections": {"admin", "manager", "quality"},
    "corrective-actions": {"admin", "manager", "quality", "supervisor"},
    "stock-lots": {"admin", "manager", "warehouse"},
    "purchase-orders": {"admin", "manager", "warehouse"},
    "purchase-order-lines": {"admin", "manager", "warehouse"},
    "sales-orders": {"admin", "manager", "planner", "commercial", "warehouse"},
    "sales-order-lines": {"admin", "manager", "planner", "commercial"},
    "production-orders": {"admin", "manager", "planner"},
    "batches": {"admin", "manager", "planner"},
    "work-assignments": {"admin", "manager", "planner", "supervisor"},
    "cutting-jobs": {"admin", "manager", "planner", "supervisor", "operator"},
    "downtimes": {"admin", "manager", "supervisor", "operator"},
    "subcontract-services": {"admin", "manager", "commercial", "planner"},
    "service-stages": {"admin", "manager", "commercial", "planner"},
    "subcontract-jobs": {"admin", "manager", "planner", "supervisor"},
    "shipments": {"admin", "manager", "warehouse"},
    "capacity-days": {"admin", "manager", "planner", "supervisor"},
    "capacity-events": {"admin", "manager", "planner", "supervisor"},
    "employee-skills": {"admin", "manager", "planner", "supervisor"},
    "external-capacities": {"admin", "manager", "planner", "commercial"},
    "sewing-plans": {"admin", "manager", "planner", "commercial"},
    "work-shifts": {"admin", "manager", "planner"},
    "process-jobs": {"admin", "manager", "planner", "supervisor", "operator"},
}

ROLE_MODULES = {
    "admin": {"*"},
    "manager": {"*"},
    "commercial": {"commercial", "subcontracting", "shipping", "erp", "tables"},
    "designer": {"design"},
    "planner": {"overview", "commercial", "design", "production", "corte", "confection", "subcontracting", "shipping", "erp", "tables", "dyeing", "printing", "weaving", "spinning", "laundry", "embroidery", "finishing"},
    "supervisor": {"overview", "production", "corte", "confection", "subcontracting", "dyeing", "printing", "weaving", "spinning", "laundry", "embroidery", "finishing"},
    "quality": {"production"},
    "warehouse": {"shipping", "erp", "tables"},
    "operator": {"production", "corte", "confection", "dyeing", "printing", "weaving", "spinning", "laundry", "embroidery", "finishing"},
    "viewer": {"overview"},
}

RESOURCE_MODULES = {
    "styles": {"design", "commercial"}, "style-revisions": {"design"}, "style-variants": {"design", "commercial"},
    "article-types": {"design"}, "bom-items": {"design", "commercial"}, "product-operations": {"design", "production", "commercial"},
    "samples": {"design"}, "developments": {"design"}, "certifications": {"design"}, "materials": {"design", "commercial", "shipping", "erp", "tables"},
    "cost-sheets": {"commercial"}, "cost-lines": {"commercial"}, "customers": {"commercial", "erp", "tables"}, "suppliers": {"commercial", "subcontracting", "shipping", "erp", "tables", "confection"},
    "banks": {"tables", "erp", "commercial", "management"}, "skill-types": {"confection", "production"}, "machine-types": {"confection", "production"},
    "sales-orders": {"commercial", "shipping"}, "sales-order-lines": {"commercial", "shipping"},
    "production-orders": {"production", "confection", "dyeing", "printing", "weaving", "spinning", "corte", "laundry", "embroidery", "finishing"}, "batches": {"production", "confection"}, "work-assignments": {"production", "confection"},
    "production-events": {"production", "confection"}, "cutting-jobs": {"production", "corte"}, "quality-inspections": {"production", "shipping", "subcontracting"},
    "corrective-actions": {"production", "shipping", "subcontracting"},
    "operations": {"design", "commercial", "production", "confection", "dyeing", "printing", "weaving", "spinning", "corte", "laundry", "embroidery", "finishing"}, "production-lines": {"design", "production", "confection", "dyeing", "printing", "weaving", "spinning", "corte"},
    "machines": {"production", "confection", "dyeing", "printing", "weaving", "spinning", "corte", "laundry", "embroidery", "finishing"}, "employees": {"design", "production", "confection", "dyeing", "printing", "weaving", "spinning", "corte", "laundry", "embroidery", "finishing"}, "employee-skills": {"confection"},
    "capacity-days": {"production", "confection"}, "capacity-events": {"production", "confection"}, "sewing-plans": {"production", "confection"},
    "external-capacities": {"confection", "subcontracting"}, "work-shifts": {"confection"},
    "subcontract-services": {"subcontracting"}, "subcontract-jobs": {"subcontracting"},
    "supplier-occurrences": {"commercial", "subcontracting", "production", "shipping", "erp", "tables", "management"},
    "stock-lots": {"shipping", "production", "erp"}, "inventory-movements": {"shipping", "production"},
    "purchase-orders": {"shipping", "erp"}, "purchase-order-lines": {"shipping", "erp"}, "shipments": {"shipping"},
    "warehouses": {"shipping", "erp", "management", "tables"}, "payment-terms": {"commercial", "erp", "management", "tables"},
    "exchange-rates": {"commercial", "management", "tables"},
    "process-jobs": {"production", "confection", "dyeing", "printing", "weaving", "spinning", "corte", "laundry", "embroidery", "finishing"},
    "overheads": {"management", "commercial"}, "departments": {"management", "production", "confection"}, "facilities": {"management", "production"},
    "field-definitions": {"management"}, "form-templates": {"management"}, "workflows": {"management"}, "audit": {"management"},
}


def require_module_access(db: Session, user: User, company_id: int, module_ids: set[str]) -> UserCompany:
    membership = require_company(db, user, company_id)
    permissions = set(membership.permissions or [])
    legacy = {"product": {"commercial", "design"}, "logistics": {"shipping", "subcontracting"}}
    permissions = set().union(*(legacy.get(item, {item}) for item in permissions)) if permissions else set()
    if "none" in permissions:
        raise HTTPException(403, "Sem acesso a este módulo")
    allowed = permissions if permissions else ROLE_MODULES.get(membership.role, set())
    if "*" not in allowed and not (allowed & module_ids):
        raise HTTPException(403, "Sem acesso a este módulo")
    return membership


def require_resource_read(db: Session, user: User, company_id: int, resource: str) -> UserCompany:
    modules = RESOURCE_MODULES.get(resource)
    return require_module_access(db, user, company_id, modules) if modules else require_company(db, user, company_id)


def require_resource_write(db: Session, user: User, company_id: int, resource: str) -> UserCompany:
    modules = RESOURCE_MODULES.get(resource)
    membership = require_module_access(db, user, company_id, modules) if modules else require_company(db, user, company_id)
    roles = RESOURCE_WRITE_ROLES.get(resource, {"admin", "manager"})
    if membership.role not in roles:
        raise HTTPException(403, "Permissão insuficiente")
    return membership
