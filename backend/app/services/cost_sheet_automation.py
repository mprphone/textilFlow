from __future__ import annotations

from datetime import date, timedelta
import unicodedata

from sqlalchemy.orm import Session

from ..models import (
    ArticleType, ArticleTypeCost, BOMItem, Company, CostLine, CostSheet, Customer,
    Material, Operation, ProductOperation, StockLot, Style, SubcontractService,
)


FABRIC_CATEGORIES = {"fabric", "knit", "woven", "malha", "tecido"}
ACCESSORY_BASELINES = (
    ("thread", {"thread", "line", "linha", "fio"}, "Linha / fio de confeção", 0.0),
    ("label", {"trim", "label", "etiqueta"}, "Etiqueta de composição", 1.0),
    ("packaging", {"packaging", "embalagem", "bag", "saco"}, "Saco / embalagem individual", 1.0),
)
LABOR_BASELINES = (
    ("cutting", ("corte", "cortar", "cut"), "Tempo de corte"),
    ("sewing", ("confec", "costur", "sewing"), "Tempo de confeção"),
    ("packing", ("embalag", "packing", "pack"), "Tempo de embalagem"),
)
AVAILABLE_LOT_STATUSES = {"available", "active", "open"}
TEMPLATE_GROUP_CATEGORIES = {
    "fabric": "material", "accessory": "material", "labor": "labor",
    "machine": "machine", "dyeing": "subcontract", "printing": "subcontract",
    "subcontract": "subcontract", "overhead": "overhead",
}


def _normalise(value: str | None) -> str:
    plain = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in plain if not unicodedata.combining(char)).lower().strip()


def _float(value, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _round(value, digits: int = 4) -> float:
    return round(_float(value), digits)


def _material_for_line(db: Session, sheet: CostSheet, line: CostLine) -> Material | None:
    source = _normalise(line.source_type)
    if source == "bom" and line.source_id:
        bom = db.get(BOMItem, line.source_id)
        if bom and bom.style_id == sheet.style_id:
            material = db.get(Material, bom.material_id)
            if material and material.company_id == sheet.company_id:
                return material
    if line.source_id and line.category == "material":
        material = db.get(Material, line.source_id)
        if material and material.company_id == sheet.company_id:
            return material
    return None


def _material_group(material: Material | None, line: CostLine) -> str:
    category = _normalise(material.category if material else None)
    source = _normalise(line.source_type)
    description = _normalise(line.description)
    if source in {"manual_fabric", "required_fabric"} or category in FABRIC_CATEGORIES:
        return "fabric"
    if any(token in description for token in ("malha", "tecido", "jersey", "fleece", "rib", "pique")):
        return "fabric"
    return "accessory"


def _accessory_baseline(material: Material | None, line: CostLine) -> str | None:
    source = _normalise(line.source_type)
    if source.startswith("required_accessory_") or source.startswith("auto_accessory_"):
        return source.rsplit("_", 1)[-1]
    category = _normalise(material.category if material else None)
    text = f"{category} {_normalise(line.description)}"
    if any(token in text for token in ("linha", "thread", "fio")):
        return "thread"
    if any(token in text for token in ("etiqueta", "label", "hangtag", "tag")):
        return "label"
    if any(token in text for token in ("embalag", "packaging", "saco", "bag", "caixa")):
        return "packaging"
    return None


def _labor_stage(db: Session, line: CostLine) -> str | None:
    source = _normalise(line.source_type)
    if source.startswith("required_labor_") or source.startswith("auto_labor_"):
        return source.rsplit("_", 1)[-1]
    text = _normalise(line.description)
    if line.source_id and "operation" in source:
        product_operation = db.get(ProductOperation, line.source_id)
        operation = db.get(Operation, product_operation.operation_id) if product_operation else None
        if operation:
            text = f"{text} {_normalise(operation.department)} {_normalise(operation.name)}"
    for key, tokens, _ in LABOR_BASELINES:
        if any(token in text for token in tokens):
            return key
    return None


def stock_unit_cost(
    db: Session, material: Material, fallback: float = 0.0, *, snapshot: dict | None = None,
) -> tuple[float, str]:
    snapshot = snapshot or material_stock_snapshot(db, material)
    if snapshot["free_quantity"] > 0 and snapshot["stock_value"] > 0:
        return snapshot["weighted_unit_cost"], "stock_weighted_average"
    if _float(material.last_cost) > 0:
        return _round(material.last_cost), "last_purchase"
    if _float(fallback) > 0:
        return _round(fallback), "bom_price"
    return _round(material.unit_cost), "material_price"


def material_stock_snapshot(db: Session, material: Material) -> dict:
    """Stock livre valorizado apenas com lotes realmente utilizáveis."""
    lots = db.query(StockLot).filter_by(company_id=material.company_id, material_id=material.id).all()
    quantity = 0.0
    value = 0.0
    for lot in lots:
        if _normalise(lot.status or "available") not in AVAILABLE_LOT_STATUSES:
            continue
        if lot.expiry_date and lot.expiry_date < date.today():
            continue
        free = max(0.0, _float(lot.quantity) - _float(lot.reserved))
        if free <= 0:
            continue
        quantity += free
        value += free * _float(lot.unit_cost)
    return {
        "free_quantity": _round(quantity),
        "stock_value": _round(value),
        "weighted_unit_cost": _round(value / quantity) if quantity > 0 and value > 0 else 0.0,
    }


def _material_cost(db: Session, material: Material, fallback: float = 0.0) -> float:
    return stock_unit_cost(db, material, fallback)[0]


def _find_material(db: Session, company_id: int, tokens: set[str]) -> Material | None:
    rows = db.query(Material).filter_by(company_id=company_id, active=True).order_by(Material.id).all()
    for row in rows:
        haystack = " ".join((_normalise(row.category), _normalise(row.tf_type), _normalise(row.name), _normalise(row.code)))
        if any(token in haystack for token in tokens):
            return row
    return None


def _find_operation(db: Session, company_id: int, tokens: tuple[str, ...]) -> Operation | None:
    rows = db.query(Operation).filter_by(company_id=company_id, active=True).order_by(Operation.id).all()
    for row in rows:
        haystack = f"{_normalise(row.department)} {_normalise(row.name)} {_normalise(row.code)}"
        if any(token in haystack for token in tokens):
            return row
    return None


def default_cost_template(db: Session, company_id: int) -> dict:
    """Estrutura mínima predefinida usada pelo assistente de novas propostas."""
    company = db.get(Company, company_id)
    settings = ((company.settings or {}).get("costing") or {}) if company else {}
    accessories = []
    for key, tokens, label, default_quantity in ACCESSORY_BASELINES:
        material = _find_material(db, company_id, tokens)
        if not material:
            accessories.append({
                "baseline": key,
                "material_id": None,
                "description": f"{label} — selecionar artigo",
                "quantity": default_quantity,
                "unit": "un" if default_quantity else "m",
                "unit_cost": 0.0,
                "cost_origin": "missing_catalog",
            })
            continue
        unit_cost, cost_origin = stock_unit_cost(db, material)
        accessories.append({
            "baseline": key,
            "material_id": material.id,
            "description": material.name,
            "quantity": _float((material.custom_data or {}).get("default_consumption"), default_quantity),
            "unit": material.unit,
            "unit_cost": unit_cost,
            "cost_origin": cost_origin,
        })
    operations = []
    for key, tokens, label in LABOR_BASELINES:
        operation = _find_operation(db, company_id, tokens)
        if not operation:
            operations.append({
                "stage": key,
                "operation_id": None,
                "description": label,
                "quantity": 0.0,
                "unit": "min",
                "unit_cost": 0.0,
            })
            continue
        operations.append({
            "stage": key,
            "operation_id": operation.id,
            "description": operation.name or label,
            "quantity": _float(operation.standard_time_min),
            "unit": "min",
            "unit_cost": _float(operation.cost_per_minute),
        })
    return {
        "accessories": accessories,
        "operations": operations,
        "overheads": [{
            "description": "Custos gerais / indiretos por peça",
            "quantity": 1,
            "unit": "un",
            "unit_cost": _float(settings.get("overhead_per_piece")),
        }],
        "pricing": {
            "financial_cost_pct": _float(settings.get("financial_cost_pct"), 2),
            "markup_pct": _float(settings.get("markup_pct"), 35),
            "commission_pct": _float(settings.get("commission_pct"), 0),
        },
    }


def suggested_article_type_costs(db: Session, article_type: ArticleType) -> list[dict]:
    """Modelo inicial seguro; o tipo pode depois acrescentar fechos, bordados, lavagens, etc."""
    base = default_cost_template(db, article_type.company_id)
    rows = [{
        "id": None,
        "article_type_id": article_type.id,
        "cost_group": "fabric",
        "role_key": "main_fabric",
        "material_id": None,
        "operation_id": None,
        "subcontract_service_id": None,
        "description": "Malha / tecido principal",
        "quantity": 0.5,
        "unit": "kg",
        "waste_pct": 5.0,
        "unit_cost": 0.0,
        "use_live_price": True,
        "required": True,
        "sequence": 10,
        "active": True,
    }]
    sequence = 20
    for item in base["accessories"]:
        rows.append({
            "id": None, "article_type_id": article_type.id, "cost_group": "accessory",
            "role_key": item["baseline"], "material_id": item.get("material_id"),
            "operation_id": None, "subcontract_service_id": None,
            "description": item["description"].replace(" — selecionar artigo", ""),
            "quantity": item["quantity"], "unit": item["unit"], "waste_pct": 0.0,
            "unit_cost": item["unit_cost"], "use_live_price": True,
            "required": True, "sequence": sequence, "active": True,
        })
        sequence += 10
    for item in base["operations"]:
        rows.append({
            "id": None, "article_type_id": article_type.id, "cost_group": "labor",
            "role_key": item["stage"], "material_id": None,
            "operation_id": item.get("operation_id"), "subcontract_service_id": None,
            "description": item["description"], "quantity": item["quantity"],
            "unit": "min", "waste_pct": 0.0, "unit_cost": item["unit_cost"],
            "use_live_price": True, "required": True, "sequence": sequence, "active": True,
        })
        sequence += 10
    overhead = base["overheads"][0]
    rows.append({
        "id": None, "article_type_id": article_type.id, "cost_group": "overhead",
        "role_key": "factory_overhead", "material_id": None, "operation_id": None,
        "subcontract_service_id": None, "description": overhead["description"],
        "quantity": overhead["quantity"], "unit": overhead["unit"], "waste_pct": 0.0,
        "unit_cost": overhead["unit_cost"], "use_live_price": False,
        "required": True, "sequence": sequence, "active": True,
    })
    return rows


def _template_unit_cost(db: Session, row) -> tuple[float, str]:
    if not row.get("use_live_price", True):
        return _round(row.get("unit_cost")), "fixed_template"
    if row.get("material_id"):
        material = db.get(Material, row["material_id"])
        if material:
            return stock_unit_cost(db, material, row.get("unit_cost", 0))
    if row.get("operation_id"):
        operation = db.get(Operation, row["operation_id"])
        if operation:
            field = "machine_cost_per_minute" if row.get("cost_group") == "machine" else "cost_per_minute"
            return _round(getattr(operation, field, 0) or row.get("unit_cost", 0)), "operation_rate"
    if row.get("subcontract_service_id"):
        service = db.get(SubcontractService, row["subcontract_service_id"])
        if service:
            return _round(service.unit_cost or row.get("unit_cost", 0)), "service_price"
    return _round(row.get("unit_cost")), "template_price"


def article_type_cost_template_view(db: Session, article_type: ArticleType) -> dict:
    stored = db.query(ArticleTypeCost).filter_by(
        company_id=article_type.company_id, article_type_id=article_type.id,
    ).order_by(ArticleTypeCost.sequence, ArticleTypeCost.id).all()
    raw = [{
        "id": row.id, "article_type_id": row.article_type_id, "cost_group": row.cost_group,
        "role_key": row.role_key, "material_id": row.material_id, "operation_id": row.operation_id,
        "subcontract_service_id": row.subcontract_service_id, "description": row.description,
        "quantity": row.quantity, "unit": row.unit, "waste_pct": row.waste_pct,
        "unit_cost": row.unit_cost, "use_live_price": row.use_live_price,
        "required": row.required, "sequence": row.sequence, "active": row.active,
    } for row in stored] if stored else suggested_article_type_costs(db, article_type)
    lines = []
    for row in raw:
        effective, origin = _template_unit_cost(db, row)
        reference = None
        if row.get("material_id"):
            reference = db.get(Material, row["material_id"])
        elif row.get("operation_id"):
            reference = db.get(Operation, row["operation_id"])
        elif row.get("subcontract_service_id"):
            reference = db.get(SubcontractService, row["subcontract_service_id"])
        lines.append({
            **row,
            "effective_unit_cost": effective,
            "price_origin": origin,
            "reference_label": getattr(reference, "name", None),
            "unit_cost_total": _round(_float(row.get("quantity")) * (1 + _float(row.get("waste_pct")) / 100) * effective),
        })
    return {
        "article_type": {
            "id": article_type.id, "company_id": article_type.company_id, "code": article_type.code,
            "name": article_type.name, "category": article_type.category,
            "default_unit": article_type.default_unit, "active": article_type.active,
        },
        "configured": bool(stored),
        "lines": lines,
        "suggested_lines": suggested_article_type_costs(db, article_type),
    }


def replace_article_type_cost_template(db: Session, article_type: ArticleType, items) -> list[ArticleTypeCost]:
    db.query(ArticleTypeCost).filter_by(
        company_id=article_type.company_id, article_type_id=article_type.id,
    ).delete(synchronize_session=False)
    rows = []
    for index, item in enumerate(items, 1):
        group = _normalise(item.cost_group).replace(" ", "_")
        if group not in TEMPLATE_GROUP_CATEGORIES:
            raise ValueError(f"Família de custo inválida: {item.cost_group}")
        links = [item.material_id, item.operation_id, item.subcontract_service_id]
        if sum(value is not None for value in links) > 1:
            raise ValueError(f"{item.description}: escolha apenas um artigo, operação ou serviço")
        if item.material_id:
            material = db.get(Material, item.material_id)
            if not material or material.company_id != article_type.company_id:
                raise ValueError(f"{item.description}: artigo de custo inválido")
            if group not in {"fabric", "accessory"}:
                raise ValueError(f"{item.description}: um artigo só pode ser malha ou acessório")
        if item.operation_id:
            operation = db.get(Operation, item.operation_id)
            if not operation or operation.company_id != article_type.company_id:
                raise ValueError(f"{item.description}: operação inválida")
            if group not in {"labor", "machine"}:
                raise ValueError(f"{item.description}: uma operação só pode ser mão de obra ou máquina")
        if item.subcontract_service_id:
            service = db.get(SubcontractService, item.subcontract_service_id)
            if not service or service.company_id != article_type.company_id:
                raise ValueError(f"{item.description}: serviço inválido")
            if group not in {"dyeing", "printing", "subcontract"}:
                raise ValueError(f"{item.description}: o serviço deve ficar num grupo de subcontratação")
        role = _normalise(item.role_key).replace(" ", "_")[:40] or f"{group}_{index}"
        row = ArticleTypeCost(
            company_id=article_type.company_id, article_type_id=article_type.id,
            cost_group=group, role_key=role, material_id=item.material_id,
            operation_id=item.operation_id, subcontract_service_id=item.subcontract_service_id,
            description=item.description.strip(), quantity=item.quantity, unit=item.unit.strip(),
            waste_pct=item.waste_pct, unit_cost=item.unit_cost,
            use_live_price=item.use_live_price, required=item.required,
            sequence=item.sequence or index * 10, active=item.active,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def _template_rows_for_sheet(db: Session, sheet: CostSheet) -> list[ArticleTypeCost]:
    style = db.get(Style, sheet.style_id)
    if not style or not style.article_type_id:
        return []
    return db.query(ArticleTypeCost).filter_by(
        company_id=sheet.company_id, article_type_id=style.article_type_id, active=True,
    ).order_by(ArticleTypeCost.sequence, ArticleTypeCost.id).all()


def _operation_id_for_line(db: Session, line: CostLine) -> int | None:
    source = _normalise(line.source_type)
    if line.category not in {"labor", "machine"} or not line.source_id:
        return None
    if source == "operation":
        product_operation = db.get(ProductOperation, line.source_id)
        return product_operation.operation_id if product_operation else None
    if source.startswith("auto_labor_") or source.startswith("article_type_cost:"):
        return line.source_id
    return None


def _cost_group_for_line(db: Session, sheet: CostSheet, line: CostLine) -> str:
    if line.category == "material":
        return "fabric" if _material_group(_material_for_line(db, sheet, line), line) == "fabric" else "accessory"
    if line.category in {"labor", "machine", "overhead"}:
        return line.category
    if line.category == "subcontract":
        text = _normalise(line.description)
        if any(token in text for token in ("tintur", "tingimento", "dye")):
            return "dyeing"
        if any(token in text for token in ("estamp", "print", "serigraf")):
            return "printing"
        return "subcontract"
    return "overhead"


def _line_matches_template(db: Session, sheet: CostSheet, line: CostLine, template: ArticleTypeCost) -> bool:
    if _normalise(line.source_type) == f"article_type_cost:{template.id}":
        return True
    if template.material_id:
        material = _material_for_line(db, sheet, line)
        return bool(material and material.id == template.material_id)
    if template.operation_id:
        return _operation_id_for_line(db, line) == template.operation_id
    if template.subcontract_service_id:
        return line.category == "subcontract" and line.source_id == template.subcontract_service_id
    if _cost_group_for_line(db, sheet, line) != template.cost_group:
        return False
    role = _normalise(template.role_key)
    if template.cost_group == "accessory" and role in {"thread", "label", "packaging"}:
        return _accessory_baseline(_material_for_line(db, sheet, line), line) == role
    if template.cost_group == "labor" and role in {"cutting", "sewing", "packing"}:
        return _labor_stage(db, line) == role
    if template.cost_group == "fabric" and role == "main_fabric":
        return True
    return _normalise(line.description) == _normalise(template.description)


def ensure_article_type_cost_lines(db: Session, sheet: CostSheet) -> int:
    templates = _template_rows_for_sheet(db, sheet)
    if not templates:
        return 0
    lines = db.query(CostLine).filter_by(cost_sheet_id=sheet.id).order_by(CostLine.id).all()
    added = 0
    for template in templates:
        if any(_line_matches_template(db, sheet, line, template) for line in lines):
            continue
        row = {
            "cost_group": template.cost_group, "material_id": template.material_id,
            "operation_id": template.operation_id, "subcontract_service_id": template.subcontract_service_id,
            "unit_cost": template.unit_cost, "use_live_price": template.use_live_price,
        }
        unit_cost, _ = _template_unit_cost(db, row)
        quantity = _float(template.quantity) * (1 + _float(template.waste_pct) / 100)
        source_id = template.material_id or template.operation_id or template.subcontract_service_id
        line = _add_line(
            db, sheet, category=TEMPLATE_GROUP_CATEGORIES.get(template.cost_group, "other"),
            description=template.description, quantity=quantity, unit=template.unit,
            unit_cost=unit_cost, source_type=f"article_type_cost:{template.id}", source_id=source_id,
        )
        lines.append(line)
        added += 1
    return added


def _add_line(
    db: Session, sheet: CostSheet, *, category: str, description: str, quantity: float,
    unit: str, unit_cost: float, source_type: str, source_id: int | None = None,
) -> CostLine:
    line = CostLine(
        company_id=sheet.company_id,
        cost_sheet_id=sheet.id,
        category=category,
        description=description,
        quantity=_round(quantity, 6),
        unit=unit,
        unit_cost=_round(unit_cost),
        amount=_round(quantity * unit_cost),
        source_type=source_type,
        source_id=source_id,
    )
    db.add(line)
    return line


def ensure_required_cost_lines(db: Session, sheet: CostSheet) -> int:
    """Completa um rascunho sem apagar trabalho manual.

    As linhas com zero são deliberadas: tornam visível o que falta configurar,
    em vez de deixar uma proposta de uma única malha parecer completa.
    """
    if sheet.status != "draft":
        return 0
    meta = dict(sheet.custom_data or {})
    if not meta.get("valid_until"):
        meta["valid_until"] = (date.today() + timedelta(days=30)).isoformat()
        sheet.custom_data = meta
    db.flush()
    added = ensure_article_type_cost_lines(db, sheet)
    if added:
        db.flush()
    lines = db.query(CostLine).filter_by(cost_sheet_id=sheet.id).order_by(CostLine.id).all()

    material_rows = [(line, _material_for_line(db, sheet, line)) for line in lines if line.category == "material"]
    if not any(_material_group(material, line) == "fabric" for line, material in material_rows):
        _add_line(
            db, sheet, category="material", description="Malha / tecido principal — selecionar artigo",
            quantity=0, unit="kg", unit_cost=0, source_type="required_fabric",
        )
        added += 1

    covered_accessories = {
        baseline for line, material in material_rows
        if _material_group(material, line) == "accessory"
        for baseline in [_accessory_baseline(material, line)] if baseline
    }
    for key, tokens, label, default_quantity in ACCESSORY_BASELINES:
        if key in covered_accessories:
            continue
        material = _find_material(db, sheet.company_id, tokens)
        if material:
            configured_quantity = _float((material.custom_data or {}).get("default_consumption"), default_quantity)
            _add_line(
                db, sheet, category="material", description=material.name,
                quantity=configured_quantity, unit=material.unit,
                unit_cost=_material_cost(db, material), source_type=f"auto_accessory_{key}", source_id=material.id,
            )
        else:
            _add_line(
                db, sheet, category="material", description=f"{label} — selecionar artigo",
                quantity=default_quantity, unit="un" if default_quantity else "m",
                unit_cost=0, source_type=f"required_accessory_{key}",
            )
        added += 1

    labor_lines = [line for line in lines if line.category == "labor"]
    covered_labor = {stage for line in labor_lines for stage in [_labor_stage(db, line)] if stage}
    for key, tokens, label in LABOR_BASELINES:
        if key in covered_labor:
            continue
        operation = _find_operation(db, sheet.company_id, tokens)
        _add_line(
            db, sheet, category="labor", description=operation.name if operation else label,
            quantity=_float(operation.standard_time_min) if operation else 0,
            unit="min", unit_cost=_float(operation.cost_per_minute) if operation else 0,
            source_type=f"auto_labor_{key}" if operation else f"required_labor_{key}",
            source_id=operation.id if operation else None,
        )
        added += 1

    if not any(line.category == "overhead" for line in lines):
        company = db.get(Company, sheet.company_id)
        settings = ((company.settings or {}).get("costing") or {}) if company else {}
        overhead = _float(settings.get("overhead_per_piece"))
        _add_line(
            db, sheet, category="overhead", description="Custos gerais / indiretos por peça",
            quantity=1, unit="un", unit_cost=overhead,
            source_type="auto_overhead" if overhead > 0 else "required_overhead",
        )
        added += 1

    if added:
        db.flush()
        from .costing import recalculate_sheet
        recalculate_sheet(db, sheet)
    return added


def pricing_summary(db: Session, sheet: CostSheet) -> dict:
    company = db.get(Company, sheet.company_id)
    meta = dict(sheet.custom_data or {})
    customer_id = meta.get("customer_id")
    customer = db.get(Customer, customer_id) if customer_id else None
    company_defaults = ((company.settings or {}).get("costing") or {}) if company else {}
    customer_defaults = ((customer.custom_data or {}).get("costing") or {}) if customer else {}

    def setting(key: str, default: float) -> float:
        return max(0.0, _float(meta.get(key, customer_defaults.get(key, company_defaults.get(key, default))), default))

    financial_pct = min(100.0, setting("financial_cost_pct", 2.0))
    markup_pct = min(500.0, setting("markup_pct", 35.0))
    commission_pct = min(99.0, setting("commission_pct", 0.0))
    base = _float(sheet.total_cost)
    financial_amount = base * financial_pct / 100
    markup_amount = base * markup_pct / 100
    recommended = (base + financial_amount + markup_amount) / (1 - commission_pct / 100)
    return {
        "base_cost": _round(base),
        "financial_cost_pct": _round(financial_pct, 2),
        "financial_cost_amount": _round(financial_amount),
        "markup_pct": _round(markup_pct, 2),
        "markup_amount": _round(markup_amount),
        "commission_pct": _round(commission_pct, 2),
        "recommended_selling_price": _round(recommended),
        "price_difference": _round(_float(sheet.selling_price) - recommended),
    }


def cost_sheet_completeness(db: Session, sheet: CostSheet) -> dict:
    lines = db.query(CostLine).filter_by(cost_sheet_id=sheet.id).order_by(CostLine.id).all()
    meta = dict(sheet.custom_data or {})
    grouped = {"fabric": [], "accessory": [], "labor": [], "overhead": []}
    raw_invalid_line_ids: list[int] = []

    for line in lines:
        if line.category == "material":
            material = _material_for_line(db, sheet, line)
            grouped[_material_group(material, line)].append(line)
        elif line.category == "labor":
            grouped["labor"].append(line)
        elif line.category == "overhead":
            grouped["overhead"].append(line)
        client_supplied = _normalise(line.source_type).startswith("client_supplied")
        if _float(line.quantity) <= 0 or (_float(line.unit_cost) <= 0 and not client_supplied):
            raw_invalid_line_ids.append(line.id)

    type_templates = _template_rows_for_sheet(db, sheet)
    optional_line_ids = {
        line.id for template in type_templates if not template.required
        for line in lines if _line_matches_template(db, sheet, line, template)
    }
    # Uma linha opcional vazia não deve ficar vermelha nem bloquear a proposta.
    # No entanto, se ela tentar ocupar um requisito universal (por exemplo a etiqueta),
    # o requisito continua incompleto e usa a lista bruta abaixo.
    invalid_line_ids = [line_id for line_id in raw_invalid_line_ids if line_id not in optional_line_ids]
    type_missing = []
    for template in type_templates:
        if not template.required:
            continue
        matches = [line for line in lines if _line_matches_template(db, sheet, line, template)]
        if not matches or not any(line.id not in raw_invalid_line_ids for line in matches):
            type_missing.append(template.description)

    labor_stages = {stage for line in grouped["labor"] for stage in [_labor_stage(db, line)] if stage}
    accessory_stages = {
        stage for line in grouped["accessory"]
        for stage in [_accessory_baseline(_material_for_line(db, sheet, line), line)] if stage
    }

    checks = []

    def add_check(key: str, label: str, complete: bool, detail: str, group: str) -> None:
        checks.append({"key": key, "label": label, "complete": bool(complete), "detail": detail, "group": group})

    add_check("customer", "Cliente associado", bool(meta.get("customer_id")), "Necessário para aceitar e emitir a proposta.", "commercial")
    add_check("valid_until", "Validade da proposta", bool(meta.get("valid_until")), "Preenchida automaticamente a 30 dias; pode alterar.", "commercial")
    if type_templates:
        add_check(
            "article_type_template", "Modelo de custos do tipo de peça", not type_missing,
            "Todos os custos obrigatórios configurados no tipo de peça estão preenchidos."
            if not type_missing else "Falta confirmar: " + ", ".join(type_missing[:4]),
            "all",
        )
    add_check(
        "cost_lines", "Custos obrigatórios por preencher", not invalid_line_ids,
        "Todas as linhas obrigatórias têm consumo e preço."
        if not invalid_line_ids else f"Existem {len(invalid_line_ids)} linha(s) obrigatória(s) ainda a zero.",
        "all",
    )
    add_check(
        "fabric", "Malha / tecido com consumo e preço",
        any(line.id not in raw_invalid_line_ids for line in grouped["fabric"]),
        "Consumo com quebra e preço corrente do material.", "fabric",
    )
    for key, _, label, _ in ACCESSORY_BASELINES:
        related = [line for line in grouped["accessory"] if _accessory_baseline(_material_for_line(db, sheet, line), line) == key]
        add_check(
            f"accessory_{key}", label,
            key in accessory_stages and any(line.id not in raw_invalid_line_ids for line in related),
            "Vem da BOM; indique apenas o consumo se ainda estiver a zero.", "accessory",
        )
    for key, _, label in LABOR_BASELINES:
        related = [line for line in grouped["labor"] if _labor_stage(db, line) == key]
        add_check(
            f"labor_{key}", label,
            key in labor_stages and any(line.id not in raw_invalid_line_ids for line in related),
            "Tempo por peça e custo por minuto.", "labor",
        )
    add_check(
        "overhead", "Custos gerais / indiretos",
        any(line.id not in raw_invalid_line_ids for line in grouped["overhead"]),
        "Rateio fabril por peça; não deve ficar implicitamente a zero.", "overhead",
    )
    add_check("selling_price", "Preço de venda", _float(sheet.selling_price) > 0, "Pode usar o preço recomendado calculado.", "commercial")
    add_check(
        "selling_above_cost", "Venda cobre o custo",
        _float(sheet.selling_price) >= _float(sheet.total_cost) > 0,
        "O preço aceite não pode ficar abaixo do custo previsto.", "commercial",
    )

    blockers = [check for check in checks if not check["complete"]]
    complete_count = len(checks) - len(blockers)
    progress = round(complete_count / len(checks) * 100) if checks else 0
    return {
        "status": "ready" if not blockers else "incomplete",
        "can_accept": not blockers,
        "progress_pct": progress,
        "complete_count": complete_count,
        "total_count": len(checks),
        "checks": checks,
        "blockers": blockers,
        "invalid_line_ids": invalid_line_ids,
    }


def refresh_automatic_costs(db: Session, sheet: CostSheet) -> int:
    """Atualiza preços ligados sem tocar em custos manuais confirmados."""
    changed = 0
    lines = db.query(CostLine).filter_by(cost_sheet_id=sheet.id).all()
    for line in lines:
        material = _material_for_line(db, sheet, line)
        source = _normalise(line.source_type)
        template = None
        if source.startswith("article_type_cost:"):
            try:
                template = db.get(ArticleTypeCost, int(source.rsplit(":", 1)[-1]))
            except (TypeError, ValueError):
                template = None
        live_template = not template or template.use_live_price
        if material and live_template and (source == "bom" or source.startswith("auto_accessory_") or source.startswith("article_type_cost:")):
            value = _material_cost(db, material, line.unit_cost)
            if value > 0 and abs(value - _float(line.unit_cost)) > 0.000001:
                line.unit_cost = value
                changed += 1
        elif live_template and line.category in {"labor", "machine"} and line.source_id and ("operation" in source or source.startswith("auto_labor_") or source.startswith("article_type_cost:")):
            operation = None
            if source == "operation":
                product_operation = db.get(ProductOperation, line.source_id)
                operation = db.get(Operation, product_operation.operation_id) if product_operation else None
            else:
                operation = db.get(Operation, line.source_id)
            rate = _float(operation.machine_cost_per_minute if line.category == "machine" else operation.cost_per_minute) if operation else 0
            if rate > 0 and abs(rate - _float(line.unit_cost)) > 0.000001:
                line.unit_cost = rate
                changed += 1
        elif live_template and line.category == "subcontract" and line.source_id and source.startswith("article_type_cost:"):
            service = db.get(SubcontractService, line.source_id)
            if service and _float(service.unit_cost) > 0 and abs(_float(service.unit_cost) - _float(line.unit_cost)) > 0.000001:
                line.unit_cost = service.unit_cost
                changed += 1
    added = ensure_required_cost_lines(db, sheet)
    if changed:
        from .costing import recalculate_sheet
        recalculate_sheet(db, sheet)
    return changed + added


def backfill_draft_cost_sheets(db: Session) -> int:
    changed = 0
    for sheet in db.query(CostSheet).filter_by(status="draft").all():
        changed += ensure_required_cost_lines(db, sheet)
    return changed
