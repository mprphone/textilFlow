"""Catálogo de documentos à imagem do ERP da empresa (Primavera, Moloni, genérico)."""

from __future__ import annotations

from datetime import date

FAMILIES = [
    {"id": "", "label": "Documentos"},
    {"id": "sales", "label": "Vendas"},
    {"id": "purchase", "label": "Compras"},
    {"id": "internal", "label": "Internos"},
    {"id": "stock", "label": "Stock"},
    {"id": "accounts", "label": "Contas correntes"},
]

INTERNAL_TYPES = {"requisition", "stock_receipt", "fabric_issue"}


def is_official(doc_type: str) -> bool:
    return doc_type not in INTERNAL_TYPES


# families: where the type appears. codes: primavera / moloni / generic
TYPE_CATALOG = {
    "sales_invoice": {
        "families": ("sales", "accounts"),
        "codes": {"primavera": "FA", "moloni": "FT", "generic": "FV"},
        "titles": {"primavera": "Fatura", "moloni": "Fatura", "generic": "Fatura de venda"},
    },
    "sales_credit": {
        "families": ("sales", "accounts"),
        "codes": {"primavera": "NC", "moloni": "NC", "generic": "NCV"},
        "titles": {"primavera": "Nota de crédito", "moloni": "Nota de crédito", "generic": "Nota de crédito a cliente"},
    },
    "sales_debit": {
        "families": ("sales", "accounts"),
        "codes": {"primavera": "ND", "moloni": "ND", "generic": "NDV"},
        "titles": {"primavera": "Nota de débito", "moloni": "Nota de débito", "generic": "Nota de débito a cliente"},
    },
    "sales_delivery": {
        "families": ("sales", "stock"),
        "codes": {"primavera": "GT", "moloni": "GT", "generic": "GT"},
        "titles": {"primavera": "Guia de transporte", "moloni": "Guia de transporte", "generic": "Guia a cliente"},
    },
    "purchase_invoice": {
        "families": ("purchase", "accounts"),
        "codes": {"primavera": "VFA", "moloni": "FC", "generic": "FC"},
        "titles": {"primavera": "Fatura de compra", "moloni": "Fatura de fornecedor", "generic": "Fatura de compra"},
    },
    "purchase_credit": {
        "families": ("purchase", "accounts"),
        "codes": {"primavera": "VNC", "moloni": "NCF", "generic": "NCC"},
        "titles": {"primavera": "NC de compra", "moloni": "NC de fornecedor", "generic": "Nota de crédito de compra"},
    },
    "purchase_debit": {
        "families": ("purchase", "accounts"),
        "codes": {"primavera": "VND", "moloni": "NDF", "generic": "NDC"},
        "titles": {"primavera": "ND de compra", "moloni": "ND de fornecedor", "generic": "Nota de débito de compra"},
    },
    "supplier_transport": {
        "families": ("purchase", "stock"),
        "codes": {"primavera": "VGT", "moloni": "GTF", "generic": "GTS"},
        "titles": {"primavera": "Guia de fornecedor", "moloni": "Guia de fornecedor", "generic": "Guia ao fornecedor"},
    },
    "requisition": {
        "families": ("internal", "purchase"),
        "codes": {"primavera": "ECF", "moloni": "ENC", "generic": "REQ"},
        "titles": {"primavera": "Encomenda a fornecedor", "moloni": "Encomenda a fornecedor", "generic": "Requisição"},
    },
    "stock_receipt": {
        "families": ("stock", "internal", "purchase"),
        "codes": {"primavera": "COM", "moloni": "ENT", "generic": "ENT"},
        "titles": {"primavera": "Entrada de existências", "moloni": "Entrada de stock", "generic": "Entrada de stock"},
    },
    "fabric_issue": {
        "families": ("internal", "stock"),
        "codes": {"primavera": "SAI", "moloni": "SAI", "generic": "SAI"},
        "titles": {"primavera": "Saída de malha", "moloni": "Saída de malha", "generic": "Saída de malha"},
    },
}

SYSTEMS = {
    "primavera": {"id": "primavera", "label": "Primavera", "editor": "Editor de documentos", "queue": "Fila Primavera"},
    "moloni": {"id": "moloni", "label": "Moloni", "editor": "Documentos Moloni", "queue": "Fila Moloni"},
    "generic": {"id": "generic", "label": "TextileFlow", "editor": "Documentos", "queue": "Fila fiscal"},
}


def detect_system(company) -> str:
    settings = dict(company.settings or {})
    explicit = str(dict(settings.get("erp") or {}).get("system") or "").strip().lower()
    if explicit in SYSTEMS:
        return explicit
    primavera = dict(settings.get("primavera") or {})
    if primavera.get("enabled") or primavera.get("base_url") or primavera.get("erp_company"):
        return "primavera"
    return "primavera"


def set_system(company, system: str) -> str:
    from sqlalchemy.orm.attributes import flag_modified
    value = system if system in SYSTEMS else "primavera"
    settings = dict(company.settings or {})
    erp = dict(settings.get("erp") or {})
    erp["system"] = value
    settings["erp"] = erp
    company.settings = settings
    if getattr(company, "id", None):
        flag_modified(company, "settings")
    return value


def _series_options(company, system: str) -> list[str]:
    cfg = dict((company.settings or {}).get("primavera") or {})
    if system == "moloni":
        year = str(date.today().year)
        return list(dict.fromkeys([cfg.get("sales_series") or year, year, "A", "1"]))
    return list(dict.fromkeys([
        cfg.get("sales_series") or "A",
        cfg.get("delivery_series") or "A",
        cfg.get("purchase_series") or "A",
        "A", "1", "B",
    ]))


def default_series(company, doc_type: str, system: str | None = None) -> str:
    system = system or detect_system(company)
    cfg = dict((company.settings or {}).get("primavera") or {})
    if doc_type in {"sales_invoice", "sales_credit", "sales_debit"}:
        return str(cfg.get("sales_series") or ("A" if system != "moloni" else str(date.today().year)))
    if doc_type in {"sales_delivery", "supplier_transport"}:
        return str(cfg.get("delivery_series") or "A")
    if doc_type.startswith("purchase") or doc_type in {"requisition", "stock_receipt", "fabric_issue"}:
        return str(cfg.get("purchase_series") or cfg.get("sales_series") or "A")
    return str(cfg.get("sales_series") or "A")


def default_code(doc_type: str, system: str) -> str:
    item = TYPE_CATALOG.get(doc_type) or {}
    return (item.get("codes") or {}).get(system) or (item.get("codes") or {}).get("generic") or doc_type


def catalog(company) -> dict:
    system = detect_system(company)
    meta = SYSTEMS[system]
    series = _series_options(company, system)
    types = []
    for key, item in TYPE_CATALOG.items():
        types.append({
            "id": key,
            "code": default_code(key, system),
            "label": (item.get("titles") or {}).get(system) or key,
            "families": list(item["families"]),
            "series": series,
            "default_series": default_series(company, key, system),
            "side": "sales" if key.startswith("sales") else ("internal" if key in INTERNAL_TYPES else "purchase"),
            "official": is_official(key),
        })
    return {
        **meta,
        "system": system,
        "families": FAMILIES,
        "types": types,
        "series": series,
    }


def identity_for(company, doc_type: str, extra: dict | None = None) -> dict:
    system = detect_system(company)
    extra = extra or {}
    return {
        "erp_system": system,
        "erp_code": extra.get("erp_code") or default_code(doc_type, system),
        "series": extra.get("series") or default_series(company, doc_type, system),
    }
