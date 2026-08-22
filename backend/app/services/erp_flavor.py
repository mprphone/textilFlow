"""Catálogo de documentos à imagem do ERP da empresa (Primavera ou genérico).

Nota: existiu aqui um terceiro "sistema" (Moloni) que só mudava rótulos e
códigos de documento - nunca teve nenhum adaptador real (nenhum cliente HTTP,
nenhuma fila própria; tudo continuava a ir para o outbox do Primavera). Foi
removido da lista para não sugerir uma integração que não existe; volta a
fazer sentido reintroduzi-lo quando (e se) houver um adaptador real."""

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

INTERNAL_TYPES = {"requisition", "stock_receipt", "fabric_issue", "internal_transfer"}


def is_official(doc_type: str) -> bool:
    return doc_type not in INTERNAL_TYPES


# families: where the type appears. codes: primavera / generic
TYPE_CATALOG = {
    "sales_invoice": {
        "families": ("sales", "accounts"),
        "codes": {"primavera": "FA", "generic": "FV"},
        "titles": {"primavera": "Fatura", "generic": "Fatura de venda"},
    },
    "sales_credit": {
        "families": ("sales", "accounts"),
        "codes": {"primavera": "NC", "generic": "NCV"},
        "titles": {"primavera": "Nota de crédito", "generic": "Nota de crédito a cliente"},
    },
    "sales_debit": {
        "families": ("sales", "accounts"),
        "codes": {"primavera": "ND", "generic": "NDV"},
        "titles": {"primavera": "Nota de débito", "generic": "Nota de débito a cliente"},
    },
    "sales_delivery": {
        "families": ("sales", "stock"),
        "codes": {"primavera": "GT", "generic": "GT"},
        "titles": {"primavera": "Guia de transporte", "generic": "Guia a cliente"},
    },
    "purchase_invoice": {
        "families": ("purchase", "accounts"),
        "codes": {"primavera": "VFA", "generic": "FC"},
        "titles": {"primavera": "Fatura de compra", "generic": "Fatura de compra"},
    },
    "purchase_credit": {
        "families": ("purchase", "accounts"),
        "codes": {"primavera": "VNC", "generic": "NCC"},
        "titles": {"primavera": "NC de compra", "generic": "Nota de crédito de compra"},
    },
    "purchase_debit": {
        "families": ("purchase", "accounts"),
        "codes": {"primavera": "VND", "generic": "NDC"},
        "titles": {"primavera": "ND de compra", "generic": "Nota de débito de compra"},
    },
    "supplier_transport": {
        "families": ("purchase", "stock"),
        "codes": {"primavera": "VGT", "generic": "GTS"},
        "titles": {"primavera": "Guia de fornecedor", "generic": "Guia ao fornecedor"},
    },
    "requisition": {
        "families": ("internal", "purchase"),
        "codes": {"primavera": "ECF", "generic": "REQ"},
        "titles": {"primavera": "Encomenda a fornecedor", "generic": "Requisição"},
    },
    "stock_receipt": {
        "families": ("stock", "internal", "purchase"),
        "codes": {"primavera": "COM", "generic": "ENT"},
        "titles": {"primavera": "Entrada de existências", "generic": "Entrada de stock"},
    },
    "fabric_issue": {
        "families": ("internal", "stock"),
        "codes": {"primavera": "SAI", "generic": "SAI"},
        "titles": {"primavera": "Saída de malha", "generic": "Saída de malha"},
    },
    "internal_transfer": {
        "families": ("internal",),
        "codes": {"primavera": "GTI", "generic": "GTI"},
        "titles": {"primavera": "Guia de transferência interna", "generic": "Guia de transferência interna"},
    },
}

SYSTEMS = {
    "primavera": {"id": "primavera", "label": "Primavera", "editor": "Editor de documentos", "queue": "Fila Primavera"},
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
        return str(cfg.get("sales_series") or "A")
    if doc_type in {"sales_delivery", "supplier_transport"}:
        return str(cfg.get("delivery_series") or "A")
    if doc_type.startswith("purchase") or doc_type in {"requisition", "stock_receipt", "fabric_issue", "internal_transfer"}:
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
