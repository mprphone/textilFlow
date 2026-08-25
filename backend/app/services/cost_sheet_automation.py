from __future__ import annotations

from datetime import date, timedelta
import unicodedata

from sqlalchemy.orm import Session

from ..models import (
    BOMItem, Company, CostLine, CostSheet, Customer, Material, Operation,
    ProductOperation, StockLot, Style,
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
    lines = db.query(CostLine).filter_by(cost_sheet_id=sheet.id).order_by(CostLine.id).all()
    added = 0

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
    invalid_line_ids: list[int] = []

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
            invalid_line_ids.append(line.id)

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
    add_check(
        "fabric", "Malha / tecido com consumo e preço",
        bool(grouped["fabric"]) and all(line.id not in invalid_line_ids for line in grouped["fabric"]),
        "Consumo com quebra e preço corrente do material.", "fabric",
    )
    for key, _, label, _ in ACCESSORY_BASELINES:
        related = [line for line in grouped["accessory"] if _accessory_baseline(_material_for_line(db, sheet, line), line) == key]
        add_check(
            f"accessory_{key}", label,
            key in accessory_stages and all(line.id not in invalid_line_ids for line in related),
            "Vem da BOM; indique apenas o consumo se ainda estiver a zero.", "accessory",
        )
    for key, _, label in LABOR_BASELINES:
        related = [line for line in grouped["labor"] if _labor_stage(db, line) == key]
        add_check(
            f"labor_{key}", label,
            key in labor_stages and all(line.id not in invalid_line_ids for line in related),
            "Tempo por peça e custo por minuto.", "labor",
        )
    add_check(
        "overhead", "Custos gerais / indiretos",
        bool(grouped["overhead"]) and all(line.id not in invalid_line_ids for line in grouped["overhead"]),
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
        if material and (source == "bom" or source.startswith("auto_accessory_")):
            value = _material_cost(db, material, line.unit_cost)
            if value > 0 and abs(value - _float(line.unit_cost)) > 0.000001:
                line.unit_cost = value
                changed += 1
        elif line.category == "labor" and line.source_id and ("operation" in source or source.startswith("auto_labor_")):
            operation = None
            if source == "operation":
                product_operation = db.get(ProductOperation, line.source_id)
                operation = db.get(Operation, product_operation.operation_id) if product_operation else None
            else:
                operation = db.get(Operation, line.source_id)
            if operation and _float(operation.cost_per_minute) > 0 and abs(_float(operation.cost_per_minute) - _float(line.unit_cost)) > 0.000001:
                line.unit_cost = operation.cost_per_minute
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
