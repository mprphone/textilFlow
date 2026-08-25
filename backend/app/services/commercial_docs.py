"""Circuito de documentos comerciais ligados ao Primavera."""

from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import (
    CommercialDocument, Company, Customer, Department, InventoryMovement, Material, ProductionLine,
    ProductionOrder, PurchaseOrder, PurchaseOrderLine, SalesOrder, SalesOrderLine, Shipment, ShipmentLine, StockLot,
    Style, StyleVariant, SubcontractService, Supplier,
)
from .company_profile import public_company
from .erp_flavor import identity_for, is_official
from .primavera import enqueue
from .serialization import model_to_dict


# Documentos que representam um movimento físico de mercadoria — aqui é que faz
# sentido perguntar "para onde vai" (o Primavera não guarda essa distinção).
MOVEMENT_DOC_TYPES = {"supplier_transport", "internal_transfer", "sales_delivery", "fabric_issue"}
AREA_LABELS = {
    "dyeing": "Tinturaria", "printing": "Estamparia", "embroidery": "Bordado", "laundry": "Lavandaria",
    "finishing": "Acabamento", "cutting": "Corte", "sewing": "Confeção / Produção", "revista": "Revista",
    "packing": "Embalagem", "warehouse": "Armazém", "transport": "Transporte", "other": "Outro",
}

DOC_TYPES = {
    "requisition": {
        "label": "Requisição a fornecedor", "prefix": "REQ", "side": "purchase",
        "kind": "requisition", "entity": "S",
    },
    "supplier_transport": {
        "label": "Guia de transporte a fornecedor", "prefix": "GTS", "side": "purchase",
        "kind": "supplier_delivery", "entity": "S",
    },
    "stock_receipt": {
        "label": "Entrada de stock", "prefix": "ENT", "side": "purchase",
        "kind": "stock_receipt", "entity": "S",
    },
    "fabric_issue": {
        "label": "Saída de malha", "prefix": "SAI", "side": "internal",
        "kind": "stock_issue", "entity": "I",
    },
    "purchase_invoice": {
        "label": "Fatura de compra", "prefix": "FC", "side": "purchase",
        "kind": "purchase_invoice", "entity": "S",
    },
    "purchase_credit": {
        "label": "Nota de crédito de compra", "prefix": "NCC", "side": "purchase",
        "kind": "purchase_credit", "entity": "S",
    },
    "purchase_debit": {
        "label": "Nota de débito de compra", "prefix": "NDC", "side": "purchase",
        "kind": "purchase_debit", "entity": "S",
    },
    "sales_invoice": {
        "label": "Fatura de venda", "prefix": "FA", "side": "sales",
        "kind": "invoice", "entity": "C",
    },
    "sales_credit": {
        "label": "Nota de crédito a cliente", "prefix": "NCV", "side": "sales",
        "kind": "sales_credit", "entity": "C",
    },
    "sales_debit": {
        "label": "Nota de débito a cliente", "prefix": "NDV", "side": "sales",
        "kind": "sales_debit", "entity": "C",
    },
    "sales_delivery": {
        "label": "Guia de transporte a cliente", "prefix": "GT", "side": "sales",
        "kind": "delivery", "entity": "C",
    },
    "internal_transfer": {
        "label": "Guia de transferência interna", "prefix": "GTI", "side": "internal",
        "kind": "internal_transfer", "entity": "I",
    },
}

CONVERT = {
    "requisition": ("purchase_invoice", "supplier_transport", "stock_receipt"),
    "supplier_transport": ("stock_receipt", "purchase_invoice"),
    "stock_receipt": ("purchase_invoice",),
    "purchase_invoice": ("purchase_credit", "purchase_debit"),
    "sales_delivery": ("sales_invoice",),
    "sales_invoice": ("sales_credit", "sales_debit"),
}


def _meta(doc_type: str) -> dict:
    if doc_type not in DOC_TYPES:
        raise HTTPException(422, "Tipo de documento desconhecido")
    return DOC_TYPES[doc_type]


def next_number(db: Session, company_id: int, doc_type: str) -> str:
    prefix = _meta(doc_type)["prefix"]
    year = date.today().year
    like = f"{prefix}-{year}-%"
    last = (
        db.query(CommercialDocument)
        .filter(CommercialDocument.company_id == company_id, CommercialDocument.doc_no.like(like))
        .order_by(CommercialDocument.id.desc())
        .first()
    )
    seq = 1
    if last:
        try:
            seq = int(str(last.doc_no).rsplit("-", 1)[-1]) + 1
        except ValueError:
            seq = 1
    return f"{prefix}-{year}-{seq:04d}"


def _total(lines: list) -> float:
    total = 0.0
    for item in lines:
        qty = float(item.get("quantity") or 0)
        price = float(item.get("unit_cost") or item.get("unit_price") or 0)
        discount = float(item.get("discount_pct") or 0)
        total += qty * price * (1 - discount / 100)
    return round(total, 4)


def _clean_lines(db: Session, company_id: int, lines: list) -> list:
    cleaned = []
    for raw in lines or []:
        material = db.get(Material, raw.get("material_id")) if raw.get("material_id") else None
        style = db.get(Style, raw.get("style_id")) if raw.get("style_id") else None
        if material and material.company_id != company_id:
            material = None
        if style and style.company_id != company_id:
            style = None
        quantity = float(raw.get("quantity") or 0)
        if quantity <= 0:
            continue
        cost = float(raw.get("unit_cost") or raw.get("unit_price") or (material.unit_cost if material else 0) or 0)
        discount = float(raw.get("discount_pct") or 0)
        amount = round(quantity * cost * (1 - discount / 100), 4)
        vat_code = str(raw.get("vat_code") or (getattr(material, "vat_code", None) if material else None) or "23")
        cleaned.append({
            "material_id": material.id if material else None,
            "style_id": style.id if style else None,
            "code": raw.get("code") or (material.code if material else None) or (style.reference if style else None) or "",
            "description": raw.get("description") or (material.name if material else None) or (style.description if style else None) or "",
            "quantity": quantity,
            "unit_cost": cost,
            "unit_price": cost,
            "discount_pct": discount,
            "amount": amount,
            "unit": raw.get("unit") or (material.unit if material else "UN"),
            "warehouse": raw.get("warehouse") or (getattr(material, "warehouse", None) if material else None) or "",
            "lot": raw.get("lot") or "",
            "vat_code": vat_code,
            "barcode": raw.get("barcode") or (getattr(material, "barcode", None) if material else None) or "",
        })
    return cleaned


def document_locked(document) -> bool:
    extra = dict(document.extra or {})
    if extra.get("locked") is False:
        return False
    if extra.get("locked") is True:
        return True
    if not is_official(document.doc_type):
        return False
    return document.primavera_status in {"queued", "prepared", "sent"} or document.status in {"prepared", "posted"}


def _append_lock_event(extra: dict, action: str, reason: str, user) -> dict:
    events = list(extra.get("lock_events") or [])
    events.append({
        "action": action,
        "reason": reason,
        "at": datetime.now().isoformat(timespec="seconds"),
        "user": getattr(user, "username", None) or "sistema",
        "user_id": getattr(user, "id", None),
    })
    extra["lock_events"] = events[-20:]
    return extra


def lock_after_send(document, user=None) -> None:
    from sqlalchemy.orm.attributes import flag_modified
    extra = _append_lock_event(dict(document.extra or {}), "lock", "Enviado para o Primavera", user)
    extra["locked"] = True
    extra["locked_at"] = datetime.now().isoformat(timespec="seconds")
    document.extra = extra
    flag_modified(document, "extra")


def unlock_document(document, user, reason: str) -> CommercialDocument:
    from sqlalchemy.orm.attributes import flag_modified
    text = (reason or "").strip()
    if len(text) < 8:
        raise HTTPException(422, "Indique o motivo do desbloqueio (mínimo 8 caracteres).")
    extra = _append_lock_event(dict(document.extra or {}), "unlock", text, user)
    extra["locked"] = False
    extra["unlocked_at"] = datetime.now().isoformat(timespec="seconds")
    extra["unlock_reason"] = text
    extra["unlocked_by"] = getattr(user, "username", None)
    document.extra = extra
    flag_modified(document, "extra")
    return document


def public_document(db: Session, document: CommercialDocument, company: Company | None = None) -> dict:
    data = model_to_dict(document)
    meta = DOC_TYPES.get(document.doc_type) or {}
    extra = dict(document.extra or {})
    locked = document_locked(document)
    supplier = db.get(Supplier, document.supplier_id) if document.supplier_id else None
    customer = db.get(Customer, document.customer_id) if document.customer_id else None
    company = company or db.get(Company, document.company_id)
    ident = identity_for(company, document.doc_type, extra) if company else {
        "erp_code": extra.get("erp_code") or meta.get("prefix"),
        "series": extra.get("series") or "A",
        "erp_system": "primavera",
    }
    data["type_label"] = meta.get("label") or document.doc_type
    data["erp_code"] = ident["erp_code"]
    data["series"] = ident["series"]
    data["erp_system"] = ident["erp_system"]
    data["side"] = meta.get("side")
    data["partner_name"] = (supplier.name if supplier else None) or (customer.name if customer else None)
    data["partner_code"] = (supplier.code if supplier else None) or (customer.code if customer else None)
    data["can_convert"] = list(CONVERT.get(document.doc_type) or [])
    data["official"] = is_official(document.doc_type)
    data["locked"] = locked
    data["can_prepare"] = is_official(document.doc_type) and document.primavera_status != "sent" and not locked
    data["primavera_done"] = document.primavera_status == "sent" or document.status == "posted"
    data["primavera_queued"] = document.primavera_status in {"queued", "pending", "prepared"}
    # O Primavera só guarda o fornecedor/cliente do documento, não a área/serviço
    # específico dentro dele (ex. qual dos vários serviços de um fornecedor, ou
    # para que área interna vai a mercadoria) — isso só fica registado aqui, em
    # extra["area"] (escolhido no editor ou pré-preenchido por from_distribution()).
    data["area"] = extra.get("area") or extra.get("service_category") or None
    data["area_detail"] = AREA_LABELS.get(data["area"]) or extra.get("service_name") or extra.get("department") or None
    data["area_from"] = extra.get("area_from") or None
    data["area_from_detail"] = AREA_LABELS.get(data["area_from"])
    data["unlock_reason"] = extra.get("unlock_reason")
    data["unlocked_by"] = extra.get("unlocked_by")
    data["lock_events"] = extra.get("lock_events") or []
    return data


def _party(entity) -> dict | None:
    if not entity:
        return None
    extra = dict(getattr(entity, "custom_data", None) or {})
    return {
        "id": entity.id,
        "code": entity.code,
        "name": entity.name,
        "tax_id": getattr(entity, "tax_id", None),
        "email": getattr(entity, "email", None),
        "phone": getattr(entity, "phone", None),
        "address": getattr(entity, "address", None) or extra.get("address"),
        "postal_code": getattr(entity, "postal_code", None),
        "city": getattr(entity, "city", None),
        "country": getattr(entity, "country", None),
        "payment_terms": getattr(entity, "payment_terms", None),
        "payment_term_code": getattr(entity, "payment_term_code", None),
        "currency": getattr(entity, "currency", None),
    }


def document_view(db: Session, company: Company, document: CommercialDocument) -> dict:
    data = public_document(db, document)
    extra = dict(document.extra or {})
    vat_pct = float(extra.get("vat_pct") if extra.get("vat_pct") not in (None, "") else 23)
    lines = []
    net = 0.0
    vat_amount = 0.0
    rates = {"23": 23.0, "13": 13.0, "6": 6.0, "0": 0.0, "ISE": 0.0}
    for line in document.lines or []:
        qty = float(line.get("quantity") or 0)
        price = float(line.get("unit_cost") or line.get("unit_price") or 0)
        discount = float(line.get("discount_pct") or 0)
        amount = round(qty * price * (1 - discount / 100), 4)
        net += amount
        rate = rates.get(str(line.get("vat_code") or ""), vat_pct)
        vat_amount += round(amount * rate / 100, 4)
        lines.append({**line, "unit_price": price, "unit_cost": price, "amount": amount, "vat_rate": rate})
    data["lines"] = lines
    data["vat_pct"] = vat_pct
    data["net_total"] = round(net, 4)
    data["vat_amount"] = vat_amount
    data["gross_total"] = round(net + vat_amount, 4)
    pub = public_company(company)
    profile = dict(pub.get("profile") or {})
    data["issuer"] = {
        "name": profile.get("legal_name") or company.name,
        "code": company.code,
        "tax_id": company.tax_id,
        "address": " ".join(part for part in [profile.get("address"), profile.get("address_extra")] if part),
        "postal_code": profile.get("postal_code"),
        "city": profile.get("city"),
        "district": profile.get("district"),
        "country": profile.get("country") or "Portugal",
        "phone": profile.get("phone"),
        "email": profile.get("email"),
        "iban": profile.get("iban"),
        "bic": profile.get("bic"),
        "cae": profile.get("cae"),
        "share_capital": profile.get("share_capital"),
    }
    data["supplier"] = _party(db.get(Supplier, document.supplier_id) if document.supplier_id else None)
    data["customer"] = _party(db.get(Customer, document.customer_id) if document.customer_id else None)
    data["partner"] = data["customer"] or data["supplier"]
    order = db.get(SalesOrder, document.sales_order_id) if document.sales_order_id else None
    purchase = db.get(PurchaseOrder, document.purchase_order_id) if document.purchase_order_id else None
    shipment = db.get(Shipment, document.shipment_id) if document.shipment_id else None
    if not shipment and order:
        shipment = (
            db.query(Shipment)
            .filter_by(company_id=company.id, sales_order_id=order.id)
            .order_by(Shipment.id.desc())
            .first()
        )
    data["references"] = {
        "sales_order": order.order_no if order else None,
        "customer_po": order.customer_po if order else None,
        "delivery_date": str(order.delivery_date) if order and order.delivery_date else None,
        "purchase_order": purchase.order_no if purchase else None,
        "converted_from": document.converted_from_id,
    }
    dest = extra.get("destination") or extra.get("shipping_address")
    if not dest and data["partner"]:
        dest = data["partner"].get("address")
    data["shipping"] = {
        "shipment_no": (shipment.shipment_no if shipment else None) or extra.get("shipment_no"),
        "carrier": (shipment.carrier if shipment else None) or extra.get("carrier"),
        "tracking_no": (shipment.tracking_no if shipment else None) or extra.get("tracking_no"),
        "destination": (shipment.destination if shipment else None) or dest,
        "quantity": float(shipment.quantity) if shipment and shipment.quantity is not None else extra.get("shipping_qty"),
        "shipped_at": shipment.shipped_at.isoformat() if shipment and shipment.shipped_at else extra.get("shipped_at"),
        "status": shipment.status if shipment else extra.get("shipping_status"),
    }
    return data


def list_documents(
    db: Session, company_id: int, doc_type: str | None = None, side: str | None = None,
    family: str | None = None, series: str | None = None,
) -> list[dict]:
    from .erp_flavor import TYPE_CATALOG
    query = db.query(CommercialDocument).filter_by(company_id=company_id).order_by(CommercialDocument.id.desc())
    if doc_type:
        query = query.filter_by(doc_type=doc_type)
    rows = query.limit(400).all()
    documents = [public_document(db, row) for row in rows]
    if side:
        documents = [row for row in documents if row.get("side") == side]
    if family:
        allowed = {key for key, item in TYPE_CATALOG.items() if family in item["families"]}
        documents = [row for row in documents if row.get("doc_type") in allowed]
    if series:
        documents = [row for row in documents if str(row.get("series") or "") == str(series)]
    return documents


def create_document(db: Session, company_id: int, payload: dict) -> CommercialDocument:
    doc_type = payload.get("doc_type") or "requisition"
    meta = _meta(doc_type)
    lines = _clean_lines(db, company_id, payload.get("lines") or [])
    company = db.get(Company, company_id)
    extra = dict(payload.get("extra") or {})
    if company:
        extra.update(identity_for(company, doc_type, extra))
    if payload.get("series"):
        extra["series"] = payload["series"]
    if payload.get("erp_code"):
        extra["erp_code"] = payload["erp_code"]
    for key in ("due_date", "your_ref", "warehouse", "commercial_discount", "additional_discount", "vat_pct"):
        if payload.get(key) not in (None, ""):
            extra[key] = payload[key]
    document = CommercialDocument(
        company_id=company_id,
        doc_type=doc_type,
        doc_no=payload.get("doc_no") or next_number(db, company_id, doc_type),
        doc_date=payload.get("doc_date") or date.today(),
        status="draft",
        supplier_id=payload.get("supplier_id"),
        customer_id=payload.get("customer_id"),
        purchase_order_id=payload.get("purchase_order_id"),
        sales_order_id=payload.get("sales_order_id"),
        shipment_id=payload.get("shipment_id"),
        converted_from_id=payload.get("converted_from_id"),
        currency=payload.get("currency") or "EUR",
        total=_total(lines),
        notes=payload.get("notes"),
        lines=lines,
        primavera_kind=meta["kind"],
        primavera_status="pending",
        extra=extra,
    )
    if payload.get("prepare") and not lines:
        raise HTTPException(422, "Indique pelo menos uma linha com quantidade")
    db.add(document)
    db.flush()
    return document


def update_document(db: Session, company: Company, document: CommercialDocument, payload: dict) -> CommercialDocument:
    from sqlalchemy.orm.attributes import flag_modified
    if document_locked(document):
        raise HTTPException(409, "Documento bloqueado depois de enviado ao Primavera. Um administrador tem de desbloquear e justificar.")
    extra = dict(document.extra or {})
    if "series" in payload and payload["series"] not in (None, ""):
        extra["series"] = str(payload["series"])
    if "erp_code" in payload and payload["erp_code"]:
        extra["erp_code"] = str(payload["erp_code"])
    if payload.get("doc_type") and payload["doc_type"] in DOC_TYPES:
        document.doc_type = payload["doc_type"]
        document.primavera_kind = _meta(payload["doc_type"])["kind"]
    extra.update(identity_for(company, payload.get("doc_type") or document.doc_type, extra))
    for key in ("due_date", "your_ref", "warehouse", "commercial_discount", "additional_discount", "vat_pct"):
        if key in payload and payload[key] not in (None, ""):
            extra[key] = payload[key]
    if "notes" in payload:
        extra["observacoes"] = payload.get("notes") or ""
    document.extra = extra
    flag_modified(document, "extra")
    if payload.get("doc_date"):
        value = payload["doc_date"]
        document.doc_date = date.fromisoformat(str(value)[:10]) if isinstance(value, str) else value
    if "notes" in payload:
        document.notes = payload.get("notes")
    if "supplier_id" in payload:
        document.supplier_id = payload.get("supplier_id") or None
    if "customer_id" in payload:
        document.customer_id = payload.get("customer_id") or None
    if "lines" in payload:
        document.lines = _clean_lines(db, company.id, payload.get("lines") or [])
        document.total = _total(document.lines)
    db.flush()
    return document


def sales_orders_overview(db: Session, company_id: int) -> list[dict]:
    """Encomendas de cliente com quantidade total, produzida e faturada — para o menu de Encomendas do ERP."""
    orders = (
        db.query(SalesOrder)
        .filter_by(company_id=company_id)
        .order_by(SalesOrder.order_date.desc().nullslast(), SalesOrder.id.desc())
        .all()
    )
    order_ids = [order.id for order in orders]
    customers = {row.id: row for row in db.query(Customer).filter(Customer.company_id == company_id).all()}

    lines = db.query(SalesOrderLine).filter(SalesOrderLine.sales_order_id.in_(order_ids or [0])).all()
    total_by_order: dict[int, float] = {}
    order_by_line: dict[int, int] = {}
    for line in lines:
        total_by_order[line.sales_order_id] = total_by_order.get(line.sales_order_id, 0.0) + float(line.quantity or 0)
        order_by_line[line.id] = line.sales_order_id

    line_ids = list(order_by_line.keys())
    produced_by_order: dict[int, float] = {}
    if line_ids:
        for production_order in db.query(ProductionOrder).filter(ProductionOrder.sales_order_line_id.in_(line_ids)).all():
            order_id = order_by_line.get(production_order.sales_order_line_id)
            if order_id:
                produced_by_order[order_id] = produced_by_order.get(order_id, 0.0) + float(production_order.completed_quantity or 0)

    invoiced_by_order: dict[int, float] = {}
    invoices = (
        db.query(CommercialDocument)
        .filter(
            CommercialDocument.company_id == company_id,
            CommercialDocument.sales_order_id.in_(order_ids or [0]),
            CommercialDocument.doc_type == "sales_invoice",
        )
        .all()
    )
    for document in invoices:
        qty = sum(float((line or {}).get("quantity") or 0) for line in (document.lines or []))
        invoiced_by_order[document.sales_order_id] = invoiced_by_order.get(document.sales_order_id, 0.0) + qty

    result = []
    for order in orders:
        customer = customers.get(order.customer_id)
        result.append({
            "id": order.id,
            "order_no": order.order_no,
            "customer_po": order.customer_po,
            "customer_id": order.customer_id,
            "customer_name": customer.name if customer else "—",
            "order_date": order.order_date.isoformat() if order.order_date else None,
            "delivery_date": order.delivery_date.isoformat() if order.delivery_date else None,
            "status": order.status,
            "quantity_total": round(total_by_order.get(order.id, 0.0), 2),
            "quantity_produced": round(produced_by_order.get(order.id, 0.0), 2),
            "quantity_invoiced": round(invoiced_by_order.get(order.id, 0.0), 2),
        })
    return result


def from_purchase_order(db: Session, company_id: int, order_id: int, doc_type: str = "requisition") -> CommercialDocument:
    order = db.get(PurchaseOrder, order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(404, "Ordem de compra não encontrada")
    rows = db.query(PurchaseOrderLine).filter_by(purchase_order_id=order.id).all()
    return create_document(db, company_id, {
        "doc_type": doc_type,
        "supplier_id": order.supplier_id,
        "purchase_order_id": order.id,
        "notes": order.notes,
        "lines": [
            {"material_id": line.material_id, "quantity": line.quantity, "unit_cost": line.unit_cost}
            for line in rows
        ],
    })


def from_sales_order(db: Session, company_id: int, order_id: int, doc_type: str = "sales_invoice") -> CommercialDocument:
    order = db.get(SalesOrder, order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(404, "Encomenda não encontrada")
    rows = db.query(SalesOrderLine).filter_by(sales_order_id=order.id).all()
    return create_document(db, company_id, {
        "doc_type": doc_type,
        "customer_id": order.customer_id,
        "sales_order_id": order.id,
        "currency": order.currency or "EUR",
        "notes": order.notes,
        "lines": [
            {
                "style_id": line.style_id, "description": line.description,
                "quantity": line.quantity, "unit_cost": line.unit_price,
            }
            for line in rows
        ],
    })


def _link_document_to_shipment(shipment: Shipment, document: CommercialDocument) -> None:
    references = [item for item in list(shipment.documents or []) if isinstance(item, dict) and int(item.get("id") or 0) != document.id]
    references.append({"id": document.id, "doc_no": document.doc_no, "doc_type": document.doc_type})
    shipment.documents = references
    if document.doc_type == "sales_invoice" and shipment.status in {"shipped", "invoiced"}:
        shipment.status = "invoiced"
    elif shipment.status == "closed":
        shipment.status = "ready"


def from_shipment(db: Session, company_id: int, shipment_id: int, doc_type: str = "sales_delivery") -> CommercialDocument:
    """Cria guia/fatura apenas com as quantidades deste packing list."""
    if doc_type not in {"sales_delivery", "sales_invoice"}:
        raise HTTPException(422, "Um packing list apenas pode gerar guia de transporte ou fatura de venda")
    shipment = db.get(Shipment, shipment_id)
    if not shipment or shipment.company_id != company_id:
        raise HTTPException(404, "Packing list não encontrado")
    if shipment.status not in {"closed", "ready", "shipped", "invoiced"}:
        raise HTTPException(409, "Feche o packing list antes de gerar documentos")
    existing = db.query(CommercialDocument).filter_by(
        company_id=company_id, shipment_id=shipment.id, doc_type=doc_type,
    ).filter(CommercialDocument.status != "cancelled").order_by(CommercialDocument.id.desc()).first()
    if existing:
        return existing
    order = db.get(SalesOrder, shipment.sales_order_id)
    if not order:
        raise HTTPException(409, "A encomenda deste packing list já não existe")
    sales_lines = {row.id: row for row in db.query(SalesOrderLine).filter_by(sales_order_id=order.id).all()}
    rows = db.query(ShipmentLine).filter_by(shipment_id=shipment.id).order_by(ShipmentLine.id).all()
    document_lines = []
    for row in rows:
        sales_line = sales_lines.get(row.sales_order_line_id)
        if not sales_line:
            continue
        variant = db.get(StyleVariant, row.variant_id) if row.variant_id else None
        variant_label = " · ".join(value for value in ((variant.color if variant else None), (variant.size if variant else None)) if value)
        description = sales_line.description or "Artigo"
        if variant_label:
            description = f"{description} — {variant_label}"
        document_lines.append({
            "style_id": sales_line.style_id,
            "description": description,
            "quantity": row.quantity,
            "unit_cost": sales_line.unit_price,
            "unit": "un",
        })
    if not document_lines:
        raise HTTPException(409, "O packing list não tem linhas faturáveis")
    document = create_document(db, company_id, {
        "doc_type": doc_type,
        "customer_id": order.customer_id,
        "sales_order_id": order.id,
        "shipment_id": shipment.id,
        "currency": order.currency or "EUR",
        "notes": f"Packing list {shipment.shipment_no}. {shipment.notes or ''}".strip(),
        "lines": document_lines,
        "extra": {
            "your_ref": order.customer_po or order.order_no,
            "shipment_no": shipment.shipment_no,
            "shipping_qty": shipment.quantity,
            "destination": shipment.destination,
            "carrier": shipment.carrier,
            "tracking_no": shipment.tracking_no,
        },
    })
    _link_document_to_shipment(shipment, document)
    return document


SOURCE_AREA = {"internal": "sewing", "revista": "revista"}


def from_distribution(
    db: Session, company_id: int, *, order_id: int, quantity: float, destination: str,
    source: str | None = None, line_id: int | None = None,
    subcontract_service_id: int | None = None, subcontract_job_id: int | None = None,
) -> CommercialDocument:
    """Prepara o documento certo a partir de uma distribuição de OF (modal Distribuir).

    Externo (serviço subcontratado) -> guia de transporte a fornecedor, com o
    serviço/categoria gravado em extra (o Primavera só sabe o fornecedor, não
    qual dos vários serviços desse fornecedor). Interno (linha de confeção) ->
    guia de transferência interna, com o departamento da linha gravado em
    extra (não existe no Primavera de todo). Em qualquer um, a área de origem
    (extra["area_from"]) vem de onde a distribuição saiu — "unassigned" não
    tem sítio físico anterior, por isso fica sem origem.
    """
    order = db.get(ProductionOrder, order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(404, "Ordem de fabrico não encontrada")
    style = db.get(Style, order.style_id)
    line_item = {
        "style_id": order.style_id,
        "code": style.reference if style else "",
        "description": style.description if style else "",
        "quantity": quantity,
        "unit": "un",
    }
    area_from = SOURCE_AREA.get(source or "")
    if destination == "subcontract":
        service = db.get(SubcontractService, subcontract_service_id) if subcontract_service_id else None
        if not service or service.company_id != company_id:
            raise HTTPException(422, "Serviço subcontratado inválido")
        return create_document(db, company_id, {
            "doc_type": "supplier_transport",
            "supplier_id": service.supplier_id,
            "notes": f"Distribuído a partir da OF {order.order_no}",
            "lines": [line_item],
            "extra": {
                "production_order_id": order.id,
                "subcontract_job_id": subcontract_job_id,
                "service_category": service.category,
                "service_name": service.name,
                "area": service.category if service.category in AREA_LABELS else "other",
                "area_from": area_from,
            },
        })
    if destination == "internal":
        line = db.get(ProductionLine, line_id) if line_id else None
        if not line or line.company_id != company_id:
            raise HTTPException(422, "Linha de confeção inválida")
        department = db.get(Department, line.department_id) if line.department_id else None
        return create_document(db, company_id, {
            "doc_type": "internal_transfer",
            "notes": f"Distribuído a partir da OF {order.order_no}",
            "lines": [line_item],
            "extra": {
                "production_order_id": order.id,
                "line_id": line.id,
                "line_name": line.name,
                "department": department.name if department else None,
                "department_id": line.department_id,
                # Não há forma fiável de mapear o nome livre do departamento para uma
                # das áreas conhecidas — fica "sewing" (confeção) como valor de partida
                # mais comum, mas o campo é editável e obrigatório antes de enviar.
                "area": "sewing",
                "area_from": area_from,
            },
        })
    if destination == "revista":
        return create_document(db, company_id, {
            "doc_type": "internal_transfer",
            "notes": f"Distribuído a partir da OF {order.order_no}",
            "lines": [line_item],
            "extra": {
                "production_order_id": order.id,
                "area": "revista",
                "area_from": area_from,
            },
        })
    raise HTTPException(422, "Destino inválido para gerar documento")


def convert_document(db: Session, company_id: int, document_id: int, doc_type: str) -> CommercialDocument:
    source = db.get(CommercialDocument, document_id)
    if not source or source.company_id != company_id:
        raise HTTPException(404, "Documento não encontrado")
    allowed = CONVERT.get(source.doc_type) or ()
    if doc_type not in allowed:
        raise HTTPException(409, f"Não é possível transformar {source.doc_no} em {_meta(doc_type)['label']}")
    replica = create_document(db, company_id, {
        "doc_type": doc_type,
        "supplier_id": source.supplier_id,
        "customer_id": source.customer_id,
        "purchase_order_id": source.purchase_order_id,
        "sales_order_id": source.sales_order_id,
        "shipment_id": source.shipment_id,
        "converted_from_id": source.id,
        "currency": source.currency,
        "notes": f"Gerado a partir de {source.doc_no}",
        "lines": source.lines or [],
        "extra": dict(source.extra or {}),
    })
    source.status = "converted"
    if source.shipment_id:
        shipment = db.get(Shipment, source.shipment_id)
        if shipment:
            _link_document_to_shipment(shipment, replica)
    if doc_type == "stock_receipt":
        receive_stock(db, company_id, replica)
    return replica


def receive_stock(db: Session, company_id: int, document: CommercialDocument) -> CommercialDocument:
    if document.doc_type != "stock_receipt":
        raise HTTPException(409, "Só uma entrada de stock cria lotes")
    extra = dict(document.extra or {})
    lots = list(extra.get("lots") or [])
    if lots:
        return document
    for index, line in enumerate(document.lines or [], start=1):
        if not line.get("material_id"):
            continue
        lot = StockLot(
            company_id=company_id,
            material_id=line["material_id"],
            supplier_id=document.supplier_id,
            lot_no=f"{document.doc_no}-{index:02d}",
            location=extra.get("location") or "Receção",
            quantity=float(line["quantity"]),
            reserved=0,
            unit_cost=float(line.get("unit_cost") or 0),
            received_date=document.doc_date or date.today(),
            status="available",
        )
        db.add(lot)
        db.flush()
        db.add(InventoryMovement(
            company_id=company_id, stock_lot_id=lot.id, movement_type="receipt",
            quantity=float(line["quantity"]), unit_cost=lot.unit_cost,
            location_to=lot.location, reference=document.doc_no,
        ))
        lots.append({"lot_id": lot.id, "lot_no": lot.lot_no, "quantity": lot.quantity})
        if document.purchase_order_id:
            for purchase_line in db.query(PurchaseOrderLine).filter_by(
                purchase_order_id=document.purchase_order_id, material_id=line["material_id"],
            ).all():
                purchase_line.received_quantity = float(purchase_line.received_quantity or 0) + float(line["quantity"])
    extra["lots"] = lots
    document.extra = extra
    document.status = "received"
    if document.purchase_order_id:
        order = db.get(PurchaseOrder, document.purchase_order_id)
        if order:
            lines = db.query(PurchaseOrderLine).filter_by(purchase_order_id=order.id).all()
            if lines and all(float(line.received_quantity or 0) + 1e-9 >= float(line.quantity or 0) for line in lines):
                order.status = "received"
            else:
                order.status = "partial"
            from .fabric_flow import notify_fabric_receipt
            extra["fabric_alerts"] = notify_fabric_receipt(
                db, company_id, purchase=order, material_ids=[line.get("material_id") for line in document.lines or [] if line.get("material_id")],
                source_no=document.doc_no,
            )
    else:
        from .fabric_flow import notify_fabric_receipt
        extra["fabric_alerts"] = notify_fabric_receipt(
            db, company_id,
            material_ids=[line.get("material_id") for line in document.lines or [] if line.get("material_id")],
            source_no=document.doc_no,
        )
    document.extra = extra
    return document


def prepare_primavera(db: Session, company: Company, document: CommercialDocument, user=None) -> dict:
    if not is_official(document.doc_type):
        raise HTTPException(409, "Documento interno: grava-se só no TextileFlow. A emissão oficial faz-se noutro tipo (FA, GT, NC…).")
    if document_locked(document):
        raise HTTPException(409, "Documento bloqueado. Um administrador tem de desbloquear e justificar antes de voltar a enviar.")
    meta = _meta(document.doc_type)
    supplier = db.get(Supplier, document.supplier_id) if document.supplier_id else None
    customer = db.get(Customer, document.customer_id) if document.customer_id else None
    extra = dict(document.extra or {})
    if meta["side"] == "purchase" and not supplier:
        raise HTTPException(422, "Indique o fornecedor antes de enviar para o Primavera.")
    if meta["side"] == "sales" and not customer:
        raise HTTPException(422, "Indique o cliente antes de enviar para o Primavera.")
    if not document.lines:
        raise HTTPException(422, "Indique pelo menos uma linha de artigo")
    if document.doc_type in MOVEMENT_DOC_TYPES and not extra.get("area"):
        raise HTTPException(422, "Indique a área de destino antes de enviar para o Primavera.")
    cfg = dict((company.settings or {}).get("primavera") or {})
    type_map = {
        "requisition": cfg.get("requisition_doc_type") or "REQ",
        "supplier_transport": cfg.get("purchase_delivery_doc_type") or "GT",
        "stock_receipt": cfg.get("goods_receipt_doc_type") or "VFA",
        "purchase_invoice": cfg.get("purchase_invoice_doc_type") or "VFA",
        "purchase_credit": cfg.get("purchase_credit_doc_type") or "NCF",
        "purchase_debit": cfg.get("purchase_debit_doc_type") or "NDF",
        "sales_invoice": cfg.get("sales_doc_type") or "FA",
        "sales_credit": cfg.get("sales_credit_doc_type") or "NC",
        "sales_debit": cfg.get("sales_debit_doc_type") or "ND",
        "sales_delivery": cfg.get("delivery_doc_type") or "GT",
    }
    series_map = {
        "purchase": cfg.get("purchase_series") or cfg.get("sales_series") or "A",
        "sales": cfg.get("sales_series") or "A",
    }
    ident = identity_for(company, document.doc_type, extra)
    payload = {
        "DocumentType": type_map.get(document.doc_type) or ident.get("erp_code"),
        "Serie": extra.get("series") or ident.get("series") or series_map.get(meta["side"]),
        "Entity": (supplier.code if supplier else None) or (customer.code if customer else None) or "",
        "EntityType": meta["entity"],
        "Warehouse": extra.get("warehouse") or cfg.get("warehouse") or "",
        "PaymentTerm": extra.get("payment_term") or (getattr(customer, "payment_term_code", None) if customer else None) or (getattr(supplier, "payment_term_code", None) if supplier else None) or "",
        "DueDate": extra.get("due_date") or str(document.doc_date or date.today()),
        "Currency": document.currency or company.currency or "EUR",
        "YourRef": extra.get("your_ref") or document.doc_no,
        "Date": str(document.doc_date or date.today()),
        "Remarks": document.notes,
        "CommercialDiscount": extra.get("commercial_discount") or 0,
        "AdditionalDiscount": extra.get("additional_discount") or 0,
        "ConvertedFrom": None,
        "Lines": [
            {
                "Item": line.get("code"),
                "Description": line.get("description"),
                "Quantity": line.get("quantity"),
                "UnitPrice": line.get("unit_price") or line.get("unit_cost"),
                "DiscountPercent": line.get("discount_pct") or 0,
                "Unit": line.get("unit"),
                "Warehouse": line.get("warehouse") or extra.get("warehouse") or "",
                "Vat": line.get("vat_code"),
                "Lot": line.get("lot"),
                "Barcode": line.get("barcode"),
            }
            for line in (document.lines or [])
        ],
        "Total": document.total,
        "TextileFlowId": document.id,
        "TextileFlowType": document.doc_type,
        "FinishInPrimavera": True,
    }
    if document.converted_from_id:
        origin = db.get(CommercialDocument, document.converted_from_id)
        payload["ConvertedFrom"] = origin.doc_no if origin else document.converted_from_id
    queued = enqueue(company, meta["kind"], payload)
    document.primavera_kind = meta["kind"]
    document.primavera_status = queued.get("status") or "queued"
    document.primavera_queue_id = queued.get("id")
    document.primavera_remote_id = queued.get("remote_id")
    document.primavera_error = queued.get("error")
    if queued.get("status") == "sent":
        document.status = "posted"
    elif document.status == "draft":
        document.status = "prepared"
    lock_after_send(document, user)
    return queued
