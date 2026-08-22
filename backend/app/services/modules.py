CORE_MODULES = (
    "overview", "commercial", "design", "production", "corte", "confection",
    "subcontracting", "shipping", "erp", "tables", "management",
)
PLANT_MODULES = (
    "dyeing", "printing", "weaving", "spinning",
    "laundry", "embroidery", "finishing",
)
ALL_MODULES = CORE_MODULES + PLANT_MODULES

PLANT_CATALOG = {
    "dyeing": {
        "kind": "dyeing", "label": "Tinturaria", "unit": "kg",
        "noun": "cuba / lote", "resource": "Cubas, receitas e lotes de malha",
        "tokens": ("tintur", "ting", "dye"),
    },
    "printing": {
        "kind": "printing", "label": "Estamparia", "unit": "un",
        "noun": "mesa / tela", "resource": "Mesas, telas e pigmentos",
        "tokens": ("estamp", "print", "serigraf"),
    },
    "weaving": {
        "kind": "weaving", "label": "Tecelagem", "unit": "m",
        "noun": "tear", "resource": "Teares, urdideiras e fios",
        "tokens": ("tecel", "tear", "weav"),
    },
    "spinning": {
        "kind": "spinning", "label": "Fiação", "unit": "kg",
        "noun": "fio / lote", "resource": "Cardas, contínuas e fios",
        "tokens": ("fia", "spin", "fio"),
    },
    "corte": {
        "kind": "cutting", "label": "Corte", "unit": "un",
        "noun": "mesa / marcador", "resource": "Mesas, cortadores e marcadores",
        "tokens": ("corte", "cut", "estend"),
    },
    "laundry": {
        "kind": "laundry", "label": "Lavandaria", "unit": "un",
        "noun": "carga", "resource": "Máquinas de lavar e receitas",
        "tokens": ("lavand", "wash", "laundry"),
    },
    "embroidery": {
        "kind": "embroidery", "label": "Bordado", "unit": "un",
        "noun": "quadro", "resource": "Máquinas de bordar e programas",
        "tokens": ("bord", "embroid"),
    },
    "finishing": {
        "kind": "finishing", "label": "Acabamento", "unit": "un",
        "noun": "linha de acabamento", "resource": "Prensas, revisões e embalagem interna",
        "tokens": ("acab", "finish"),
    },
}


def default_enabled_modules() -> list[str]:
    return list(CORE_MODULES)


def _place_corte(selected: list[str]) -> list[str]:
    has_corte = "corte" in selected
    if "confection" in selected and not has_corte:
        has_corte = True
        selected = list(selected)
    if not has_corte:
        return selected
    selected = [item for item in selected if item != "corte"]
    if "confection" in selected:
        selected.insert(selected.index("confection"), "corte")
    elif "production" in selected:
        selected.insert(selected.index("production") + 1, "corte")
    else:
        selected.append("corte")
    return selected


def enabled_modules(company) -> list[str]:
    settings = getattr(company, "settings", None) or {}
    selected = settings.get("enabled_modules")
    if not selected:
        return default_enabled_modules()
    allowed = set(ALL_MODULES)
    selected = [item for item in selected if item in allowed]
    if "erp" in selected and "tables" not in selected:
        selected.insert(selected.index("erp") + 1, "tables")
    return _place_corte(selected)


def set_enabled_modules(company, module_ids: list[str]) -> list[str]:
    allowed = set(ALL_MODULES)
    selected = [item for item in module_ids if item in allowed]
    if "overview" not in selected:
        selected = ["overview", *selected]
    selected = _place_corte(selected)
    settings = dict(getattr(company, "settings", None) or {})
    settings["enabled_modules"] = selected
    company.settings = settings
    return selected


def company_session(company, membership) -> dict:
    from .erp_flavor import detect_system, SYSTEMS
    system = detect_system(company)
    return {
        "id": company.id,
        "code": company.code,
        "name": company.name,
        "tax_id": company.tax_id,
        "legal_name": (dict((company.settings or {}).get("profile") or {}).get("legal_name") or company.name),
        "address": dict((company.settings or {}).get("profile") or {}).get("address"),
        "postal_code": dict((company.settings or {}).get("profile") or {}).get("postal_code"),
        "city": dict((company.settings or {}).get("profile") or {}).get("city"),
        "phone": dict((company.settings or {}).get("profile") or {}).get("phone"),
        "email": dict((company.settings or {}).get("profile") or {}).get("email"),
        "logo": dict((company.settings or {}).get("profile") or {}).get("logo"),
        "role": membership.role,
        "permissions": membership.permissions or [],
        "enabled_modules": enabled_modules(company),
        "erp_system": system,
        "erp_label": SYSTEMS[system]["label"],
    }


def ensure_company_modules(db) -> None:
    from sqlalchemy.orm.attributes import flag_modified
    from ..models import Company
    for company in db.query(Company).all():
        settings = dict(company.settings or {})
        selected = list(settings.get("enabled_modules") or [])
        if not selected:
            selected = default_enabled_modules()
        elif "erp" not in selected:
            insert_at = selected.index("shipping") + 1 if "shipping" in selected else len(selected)
            selected.insert(insert_at, "erp")
        if "erp" in selected and "tables" not in selected:
            selected.insert(selected.index("erp") + 1, "tables")
        selected = _place_corte(selected)
        settings["enabled_modules"] = selected
        company.settings = settings
        if getattr(company, "id", None):
            flag_modified(company, "settings")
