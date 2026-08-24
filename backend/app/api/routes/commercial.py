from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import CommercialDocument, Company, User
from ...services.commercial_docs import (
    DOC_TYPES, convert_document, create_document, document_view, from_purchase_order,
    from_sales_order, list_documents, prepare_primavera, public_document, receive_stock,
    sales_orders_overview, unlock_document, update_document,
)
from ...services.erp_flavor import catalog as erp_catalog, set_system
from ..deps import current_user, require_module_access, require_role


router = APIRouter(prefix="/erp", tags=["Documentos Primavera"])


def _company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Empresa não encontrada")
    return company


def _document(db: Session, company_id: int, document_id: int) -> CommercialDocument:
    document = db.get(CommercialDocument, document_id)
    if not document or document.company_id != company_id:
        raise HTTPException(404, "Documento não encontrado")
    return document


@router.get("/{company_id}/documents/types")
def document_types(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"erp", "shipping", "commercial", "management"})
    catalog = erp_catalog(_company(db, company_id))
    catalog["legacy"] = [{"id": key, **value} for key, value in DOC_TYPES.items()]
    return catalog


@router.put("/{company_id}/erp-system")
def set_erp_system(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin"})
    require_module_access(db, user, company_id, {"erp", "management"})
    company = _company(db, company_id)
    set_system(company, str(payload.get("system") or "primavera"))
    db.commit()
    return erp_catalog(company)


@router.get("/{company_id}/sales-orders")
def erp_sales_orders(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"erp", "shipping", "commercial", "management"})
    return sales_orders_overview(db, company_id)


@router.get("/{company_id}/documents")
def documents(
    company_id: int,
    doc_type: str | None = Query(default=None),
    side: str | None = Query(default=None),
    family: str | None = Query(default=None),
    series: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_module_access(db, user, company_id, {"erp", "shipping", "commercial", "management"})
    return list_documents(db, company_id, doc_type, side, family, series)


@router.get("/{company_id}/documents/{document_id}")
def document_detail(company_id: int, document_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"erp", "shipping", "commercial", "management"})
    return document_view(db, _company(db, company_id), _document(db, company_id, document_id))


@router.post("/{company_id}/documents", status_code=201)
def create(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "warehouse", "commercial"})
    require_module_access(db, user, company_id, {"erp", "shipping", "commercial", "management"})
    document = create_document(db, company_id, payload)
    if payload.get("prepare"):
        prepare_primavera(db, _company(db, company_id), document, user)
    db.commit()
    db.refresh(document)
    return public_document(db, document)


@router.put("/{company_id}/documents/{document_id}")
def update(company_id: int, document_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "warehouse", "commercial"})
    require_module_access(db, user, company_id, {"erp", "shipping", "commercial", "management"})
    document = update_document(db, _company(db, company_id), _document(db, company_id, document_id), payload)
    db.commit()
    db.refresh(document)
    return public_document(db, document)


@router.post("/{company_id}/documents/from-purchase/{order_id}", status_code=201)
def from_purchase(company_id: int, order_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "warehouse", "commercial"})
    require_module_access(db, user, company_id, {"erp", "shipping", "commercial"})
    document = from_purchase_order(db, company_id, order_id, payload.get("doc_type") or "requisition")
    company = _company(db, company_id)
    if payload.get("series"):
        update_document(db, company, document, {"series": payload.get("series")})
    if payload.get("prepare", True):
        prepare_primavera(db, company, document, user)
    db.commit()
    db.refresh(document)
    return public_document(db, document)


@router.post("/{company_id}/documents/from-sales/{order_id}", status_code=201)
def from_sales(company_id: int, order_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "warehouse", "commercial"})
    require_module_access(db, user, company_id, {"erp", "shipping", "commercial"})
    document = from_sales_order(db, company_id, order_id, payload.get("doc_type") or "sales_invoice")
    company = _company(db, company_id)
    if payload.get("series"):
        update_document(db, company, document, {"series": payload.get("series")})
    if payload.get("prepare", True):
        prepare_primavera(db, company, document, user)
    db.commit()
    db.refresh(document)
    return public_document(db, document)


@router.post("/{company_id}/documents/{document_id}/convert", status_code=201)
def convert(company_id: int, document_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "warehouse", "commercial"})
    require_module_access(db, user, company_id, {"erp", "shipping", "commercial"})
    document = convert_document(db, company_id, document_id, payload.get("doc_type"))
    if payload.get("prepare", True):
        prepare_primavera(db, _company(db, company_id), document, user)
    db.commit()
    db.refresh(document)
    return public_document(db, document)


@router.post("/{company_id}/documents/{document_id}/prepare")
def prepare(company_id: int, document_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "warehouse", "commercial"})
    require_module_access(db, user, company_id, {"erp", "shipping", "commercial", "management"})
    document = _document(db, company_id, document_id)
    queued = prepare_primavera(db, _company(db, company_id), document, user)
    db.commit()
    db.refresh(document)
    return {"document": public_document(db, document), "queue": queued}


@router.post("/{company_id}/documents/{document_id}/unlock")
def unlock(company_id: int, document_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin"})
    require_module_access(db, user, company_id, {"erp", "shipping", "commercial", "management"})
    document = _document(db, company_id, document_id)
    unlock_document(document, user, payload.get("reason") or payload.get("justification") or "")
    db.commit()
    db.refresh(document)
    return public_document(db, document)


@router.post("/{company_id}/documents/{document_id}/receive")
def receive(company_id: int, document_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role(db, user, company_id, {"admin", "manager", "warehouse"})
    require_module_access(db, user, company_id, {"erp", "shipping"})
    document = _document(db, company_id, document_id)
    if document.doc_type != "stock_receipt":
        document = convert_document(db, company_id, document.id, "stock_receipt")
    else:
        receive_stock(db, company_id, document)
    prepare_primavera(db, _company(db, company_id), document, user)
    db.commit()
    db.refresh(document)
    return public_document(db, document)


@router.get("/{company_id}/capture/status")
def capture_status(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ...services.capture import gemini_configured
    require_module_access(db, user, company_id, {"erp", "management"})
    return {"gemini_configured": gemini_configured(_company(db, company_id))}


@router.put("/{company_id}/capture/key")
def capture_key(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ...services.capture import gemini_configured, save_gemini_key
    require_role(db, user, company_id, {"admin"})
    require_module_access(db, user, company_id, {"erp", "management"})
    company = _company(db, company_id)
    key = str(payload.get("api_key") or "").strip()
    if not key:
        raise HTTPException(422, "Indique a chave da API Gemini")
    save_gemini_key(company, key)
    db.commit()
    return {"gemini_configured": gemini_configured(company)}


@router.post("/{company_id}/capture/read")
def capture_read(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ...services.capture import parse_document, preview_capture
    require_role(db, user, company_id, {"admin", "manager", "warehouse", "commercial"})
    require_module_access(db, user, company_id, {"erp"})
    company = _company(db, company_id)
    parsed = parse_document(company, mime=str(payload.get("mime") or "image/jpeg"), data_b64=str(payload.get("data") or ""))
    return preview_capture(db, company, parsed)


@router.post("/{company_id}/capture/confirm", status_code=201)
def capture_confirm(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ...services.capture import confirm_capture
    require_role(db, user, company_id, {"admin", "manager", "warehouse", "commercial"})
    require_module_access(db, user, company_id, {"erp"})
    company = _company(db, company_id)
    document = confirm_capture(db, company, payload)
    db.commit()
    return document


@router.get("/{company_id}/aliases")
def aliases(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ...services.capture import list_aliases
    require_module_access(db, user, company_id, {"erp"})
    return list_aliases(db, company_id)


@router.post("/{company_id}/aliases", status_code=201)
def create_alias(company_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ...services.capture import list_aliases, remember_alias
    require_role(db, user, company_id, {"admin", "manager", "warehouse", "commercial"})
    require_module_access(db, user, company_id, {"erp"})
    if not payload.get("material_id"):
        raise HTTPException(422, "Escolha o artigo TextileFlow")
    remember_alias(
        db, company_id, payload.get("supplier_id"),
        str(payload.get("source_code") or ""), str(payload.get("source_name") or ""),
        int(payload["material_id"]),
    )
    db.commit()
    return list_aliases(db, company_id)
