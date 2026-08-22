from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
import unicodedata

from sqlalchemy.orm import Session

from ..models import (
    BOMItem, CostLine, CostSheet, Customer, Material, ProductionLine,
    ProductionMaterialRequirement, ProductionOrder, ProposalProductionRelease,
    SalesOrder, SalesOrderLine, StockLot, Style, SubcontractService,
)
from .serialization import model_to_dict


ACCEPTED_STATUSES = {"approved", "production"}
RELEASABLE_STATUSES = {"approved"}
COST_GROUPS = (
    "fabric", "accessories", "labor", "machine", "dyeing", "printing",
    "subcontract_other", "overhead", "other",
)
AVAILABLE_LOT_STATUSES = {"available", "active", "open"}


class ReleaseValidationError(ValueError):
    pass


class ReleaseConflictError(ValueError):
    pass


def _round(value: float | None, digits: int = 4) -> float:
    return round(float(value or 0), digits)


def _normalise(value: str | None) -> str:
    plain = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in plain if not unicodedata.combining(char)).lower().strip()


def _material_for_line(
    db: Session, sheet: CostSheet, line: CostLine, visited: set[int] | None = None,
) -> Material | None:
    visited = visited or set()
    if line.id in visited:
        return None
    visited.add(line.id)
    source_type = (line.source_type or "").lower()
    material = None
    if source_type == "bom" and line.source_id:
        bom = db.get(BOMItem, line.source_id)
        material = db.get(Material, bom.material_id) if bom and bom.style_id == sheet.style_id else None
    elif source_type == "revision" and line.source_id:
        source = db.get(CostLine, line.source_id)
        if source:
            material = _material_for_line(db, sheet, source, visited)
    elif line.source_id and (
        source_type in {"wizard_material", "wizard_accessory", "material", "manual_verified"}
        or line.category == "material"
    ):
        candidate = db.get(Material, line.source_id)
        material = candidate if candidate and candidate.company_id == sheet.company_id else None
    if material and material.company_id == sheet.company_id:
        return material
    if line.category != "material":
        return None
    description = (line.description or "").strip()
    return db.query(Material).filter(
        Material.company_id == sheet.company_id,
        (Material.name == description) | (Material.code == description),
    ).first()


def classify_cost_line(db: Session, sheet: CostSheet, line: CostLine) -> dict:
    source_type = (line.source_type or "manual").lower()
    material = _material_for_line(db, sheet, line)
    material_category = (material.category or "other").lower() if material else None
    description = _normalise(line.description)
    source_label = "Introducao manual"

    if line.category == "material":
        fabric_categories = {"fabric", "knit", "woven", "malha", "tecido"}
        explicit_fabric = source_type in {"manual_fabric", "fabric"}
        explicit_accessory = source_type in {"manual_accessory", "accessory", "accessories"}
        cost_group = "fabric" if explicit_fabric or (
            not explicit_accessory and material_category in fabric_categories
        ) else "accessories"
        if source_type == "bom":
            source_label = "BOM / ficha tecnica"
        elif source_type == "wizard_accessory":
            source_label = "Acessorio da proposta"
        elif source_type == "wizard_material":
            source_label = "Material da proposta"
        elif source_type == "revision":
            source_label = "Revisao da proposta"
    elif line.category == "labor":
        cost_group = "labor"
        source_label = "Gama operatoria" if "operation" in source_type else "Mao de obra"
    elif line.category == "machine":
        cost_group = "machine"
        source_label = "Custo de maquina"
    elif line.category == "subcontract":
        service = db.get(SubcontractService, line.source_id) if source_type == "subcontract_service" and line.source_id else None
        service_category = _normalise(service.category if service else None)
        if (
            source_type in {"manual_dyeing", "dyeing", "dye"}
            or service_category in {"dyeing", "dye", "tinturaria", "tingimento"}
            or any(token in description for token in ("ting", "tintur", "dye"))
        ):
            cost_group, source_label = "dyeing", "Tinturaria"
        elif (
            source_type in {"manual_printing", "printing", "print"}
            or service_category in {"printing", "print", "estamparia", "screen_printing"}
            or any(token in description for token in ("estamp", "print", "serigraf"))
        ):
            cost_group, source_label = "printing", "Estamparia"
        else:
            cost_group, source_label = "subcontract_other", "Outro subcontrato"
    elif line.category == "overhead":
        cost_group, source_label = "overhead", "Custos indiretos"
    else:
        cost_group, source_label = "other", "Outros custos"
    return {
        "cost_group": cost_group,
        "source_label": source_label,
        "material_id": material.id if material else None,
        "material_category": material_category,
        "material_unit": material.unit if material else None,
    }


def annotated_cost_lines(db: Session, sheet: CostSheet) -> list[dict]:
    result = []
    rows = db.query(CostLine).filter_by(cost_sheet_id=sheet.id).order_by(CostLine.category, CostLine.id).all()
    for row in rows:
        result.append({**model_to_dict(row), **classify_cost_line(db, sheet, row)})
    return result


def category_breakdown(db: Session, sheet: CostSheet, quantity: float | None = None) -> dict:
    order_quantity = float(quantity if quantity is not None else sheet.quantity_basis or 0)
    groups = {key: {"unit_cost": 0.0, "total_cost": 0.0, "line_count": 0} for key in COST_GROUPS}
    for line in db.query(CostLine).filter_by(cost_sheet_id=sheet.id).all():
        group = classify_cost_line(db, sheet, line)["cost_group"]
        unit_cost = float(line.amount or 0)
        groups[group]["unit_cost"] += unit_cost
        groups[group]["total_cost"] += unit_cost * order_quantity
        groups[group]["line_count"] += 1
    for values in groups.values():
        values["unit_cost"] = _round(values["unit_cost"])
        values["total_cost"] = _round(values["total_cost"])
    material_unit = groups["fabric"]["unit_cost"] + groups["accessories"]["unit_cost"]
    subcontract_unit = sum(groups[key]["unit_cost"] for key in ("dyeing", "printing", "subcontract_other"))
    total_unit = sum(groups[key]["unit_cost"] for key in COST_GROUPS)
    groups["materials"] = {"unit_cost": _round(material_unit), "total_cost": _round(material_unit * order_quantity)}
    groups["subcontracts"] = {"unit_cost": _round(subcontract_unit), "total_cost": _round(subcontract_unit * order_quantity)}
    groups["total"] = {"unit_cost": _round(total_unit), "total_cost": _round(total_unit * order_quantity)}
    return groups


def _lot_sort_key(lot: StockLot) -> tuple:
    return (lot.expiry_date is None, lot.expiry_date or date.max, lot.received_date is None, lot.received_date or date.max, lot.id)


def material_requirements_preview(
    db: Session, sheet: CostSheet, quantity: float | None = None, *, lock_stock: bool = False,
) -> list[dict]:
    order_quantity = float(quantity if quantity is not None else sheet.quantity_basis or 0)
    material_lines = db.query(CostLine).filter_by(cost_sheet_id=sheet.id, category="material").order_by(CostLine.id).all()
    classified = [(line, classify_cost_line(db, sheet, line)) for line in material_lines]
    material_ids = {info["material_id"] for _, info in classified if info["material_id"]}
    lots_by_material: dict[int, list[StockLot]] = defaultdict(list)
    if material_ids:
        query = db.query(StockLot).filter(
            StockLot.company_id == sheet.company_id,
            StockLot.material_id.in_(material_ids),
        ).order_by(StockLot.id)
        if lock_stock:
            query = query.with_for_update()
        for lot in query.all():
            if (
                _normalise(lot.status or "available") in AVAILABLE_LOT_STATUSES
                and (not lot.expiry_date or lot.expiry_date >= date.today())
            ):
                lots_by_material[lot.material_id].append(lot)
    for lots in lots_by_material.values():
        lots.sort(key=_lot_sort_key)
    remaining = {
        lot.id: max(0.0, float(lot.quantity or 0) - float(lot.reserved or 0))
        for lots in lots_by_material.values() for lot in lots
    }

    requirements = []
    for line, info in classified:
        unit_required = max(0.0, float(line.quantity or 0))
        required = unit_required * order_quantity
        planned_unit_cost = max(0.0, float(line.unit_cost or 0))
        material_id = info["material_id"]
        material_lots = lots_by_material.get(material_id, []) if material_id else []
        material_unit = info["material_unit"]
        unit_mismatch = bool(material_unit and line.unit and _normalise(material_unit) != _normalise(line.unit))
        available = 0.0 if unit_mismatch else sum(remaining[lot.id] for lot in material_lots)
        available_value = 0.0 if unit_mismatch else sum(remaining[lot.id] * float(lot.unit_cost or 0) for lot in material_lots)
        average_unit_cost = available_value / available if available else planned_unit_cost
        needed = required
        allocated = 0.0
        allocated_cost = 0.0
        lot_views = []
        if material_id and not unit_mismatch:
            for lot in material_lots:
                lot_available = remaining[lot.id]
                take = min(lot_available, needed)
                if lot_available > 0:
                    lot_views.append({
                        "lot_id": lot.id, "lot_no": lot.lot_no, "location": lot.location,
                        "available_quantity": _round(lot_available, 6),
                        "allocated_quantity": _round(take, 6), "unit_cost": _round(lot.unit_cost),
                        "expiry_date": lot.expiry_date.isoformat() if lot.expiry_date else None,
                    })
                if take > 0:
                    remaining[lot.id] -= take
                    needed -= take
                    allocated += take
                    allocated_cost += take * float(lot.unit_cost or 0)
                if needed <= 1e-9:
                    break
        shortage = max(0.0, required - allocated)
        estimated_amount = allocated_cost + shortage * planned_unit_cost
        real_unit_cost = estimated_amount / required if required else planned_unit_cost
        if not material_id:
            status = "unlinked_material"
        elif unit_mismatch:
            status = "unit_mismatch"
        elif shortage > 1e-9:
            status = "shortage"
        else:
            status = "ready"
        requirements.append({
            "cost_line_id": line.id,
            "material_id": material_id,
            "description": line.description,
            "material_category": info["material_category"] or "unlinked",
            "cost_group": info["cost_group"],
            "source_label": info["source_label"],
            "unit": line.unit,
            "unit_required": _round(unit_required, 6),
            "required_quantity": _round(required, 6),
            "available_quantity": _round(available, 6),
            "allocatable_quantity": _round(allocated, 6),
            "shortage_quantity": _round(shortage, 6),
            "reserved_quantity": 0.0,
            "planned_unit_cost": _round(planned_unit_cost),
            "average_unit_cost": _round(average_unit_cost),
            "real_unit_cost": _round(real_unit_cost),
            "stock_valuation_unit_cost": _round(real_unit_cost),
            "estimated_amount": _round(estimated_amount),
            "lots": lot_views,
            "status": status,
        })
    return requirements


def stock_summary(requirements: list[dict]) -> dict:
    total = len(requirements)
    ready = sum(1 for row in requirements if float(row.get("shortage_quantity") or 0) <= 1e-9)
    coverages = [
        min(1.0, max(0.0, 1 - float(row.get("shortage_quantity") or 0) / float(row["required_quantity"])))
        for row in requirements if float(row.get("required_quantity") or 0) > 0
    ]
    return {
        "total_items": total,
        "ready_items": ready,
        "shortage_items": total - ready,
        "reserved_items": sum(1 for row in requirements if float(row.get("reserved_quantity") or 0) > 0),
        "coverage_pct": round(sum(coverages) / len(coverages) * 100, 2) if coverages else 100.0,
        "estimated_material_cost": _round(sum(float(row.get("estimated_amount") or 0) for row in requirements)),
    }


def stored_requirements(db: Session, release: ProposalProductionRelease) -> list[dict]:
    sheet = db.get(CostSheet, release.cost_sheet_id)
    result = []
    rows = db.query(ProductionMaterialRequirement).filter_by(release_id=release.id).order_by(ProductionMaterialRequirement.id).all()
    for row in rows:
        line = db.get(CostLine, row.cost_line_id)
        info = classify_cost_line(db, sheet, line) if sheet and line else {}
        result.append({
            **model_to_dict(row),
            "planned_unit_cost": _round(line.unit_cost) if line else _round(row.average_unit_cost),
            "stock_valuation_unit_cost": _round(row.real_unit_cost),
            "cost_group": info.get("cost_group", "accessories"),
            "source_label": info.get("source_label", "Necessidade da OF"),
        })
    return result


def get_release(db: Session, sheet_id: int) -> ProposalProductionRelease | None:
    return db.query(ProposalProductionRelease).filter_by(cost_sheet_id=sheet_id).first()


def production_preview(db: Session, sheet: CostSheet, quantity: float | None = None) -> dict:
    release = get_release(db, sheet.id)
    if release:
        requirements = stored_requirements(db, release)
        requested_quantity = float(release.quantity)
    else:
        requested_quantity = float(quantity if quantity is not None else sheet.quantity_basis or 0)
        requirements = material_requirements_preview(db, sheet, requested_quantity)
    lines = db.query(CostLine).filter_by(cost_sheet_id=sheet.id).all()
    meta = sheet.custom_data or {}
    style = db.get(Style, sheet.style_id)
    blockers = []
    if not release and sheet.status not in RELEASABLE_STATUSES:
        blockers.append("Aceite a proposta antes de a lancar em producao")
    if not lines or float(sheet.total_cost or 0) <= 0:
        blockers.append("A proposta precisa de linhas de custo validas")
    if float(sheet.selling_price or 0) <= 0:
        blockers.append("A proposta precisa de preco de venda")
    if not (meta.get("customer_id") or (style.customer_id if style else None)) and not release:
        blockers.append("A proposta precisa de cliente")
    if requested_quantity <= 0:
        blockers.append("A quantidade tem de ser superior a zero")
    warnings = []
    labor_minutes = 0.0
    unknown_labor_units = set()
    subcontracts = []
    for line in lines:
        if line.category == "labor":
            unit = _normalise(line.unit)
            if unit in {"min", "minute", "minutes", "minuto", "minutos"}:
                labor_minutes += float(line.quantity or 0) * requested_quantity
            elif unit in {"h", "hr", "hour", "hours", "hora", "horas"}:
                labor_minutes += float(line.quantity or 0) * 60 * requested_quantity
            else:
                unknown_labor_units.add(line.unit or "sem unidade")
        elif line.category == "subcontract":
            info = classify_cost_line(db, sheet, line)
            subcontracts.append({
                "cost_line_id": line.id,
                "description": line.description,
                "cost_group": info["cost_group"],
                "unit_cost": _round(line.amount),
                "amount": _round(float(line.amount or 0) * requested_quantity),
            })
    summary = stock_summary(requirements)
    planned_material_total = _round(float(sheet.material_cost or 0) * requested_quantity)
    stock_material_total = _round(summary["estimated_material_cost"])
    variance_total = _round(stock_material_total - planned_material_total)
    planned_material_unit = _round(sheet.material_cost)
    stock_material_unit = _round(stock_material_total / requested_quantity) if requested_quantity else 0.0
    cost_variance = {
        "planned_material_unit_cost": planned_material_unit,
        "stock_material_unit_cost": stock_material_unit,
        "unit_variance": _round(stock_material_unit - planned_material_unit),
        "planned_material_total": planned_material_total,
        "stock_material_total": stock_material_total,
        "total_variance": variance_total,
        "variance_pct": round(variance_total / planned_material_total * 100, 2) if planned_material_total else (100.0 if stock_material_total else 0.0),
    }
    if summary["shortage_items"]:
        warnings.append(f'{summary["shortage_items"]} material(is) com falta de stock')
    if unknown_labor_units:
        warnings.append("Unidades de mao de obra por normalizar: " + ", ".join(sorted(unknown_labor_units)))
    return {
        "sheet_id": sheet.id,
        "status": sheet.status,
        "quantity": _round(requested_quantity, 6),
        "can_release": not blockers,
        "already_released": bool(release),
        "blockers": blockers,
        "warnings": warnings,
        "category_breakdown": category_breakdown(db, sheet, requested_quantity),
        "requirements": requirements,
        "stock_summary": summary,
        "cost_variance": cost_variance,
        "labor_minutes": _round(labor_minutes, 2),
        "subcontracts": subcontracts,
        "production_order_id": release.production_order_id if release else meta.get("production_order_id"),
        "released_at": release.released_at.isoformat() if release and release.released_at else meta.get("released_at"),
    }


def _unique_order_no(db: Session, model, company_id: int, requested: str | None, base: str) -> str:
    value = (requested or "").strip()
    if value:
        if db.query(model).filter_by(company_id=company_id, order_no=value).first():
            raise ReleaseConflictError(f"Ja existe um documento com o numero {value}")
        return value
    value = base
    suffix = 2
    while db.query(model).filter_by(company_id=company_id, order_no=value).first():
        value = f"{base}-{suffix}"
        suffix += 1
    return value


def _persist_requirements(
    db: Session, release: ProposalProductionRelease, production_order: ProductionOrder,
    preview: list[dict], reserve_stock: bool,
) -> list[ProductionMaterialRequirement]:
    rows = []
    for item in preview:
        reserved = 0.0
        lots = []
        for allocation in item["lots"]:
            allocated = float(allocation.get("allocated_quantity") or 0)
            lot_view = dict(allocation)
            lot_view["reserved_quantity"] = _round(allocated if reserve_stock else 0, 6)
            lots.append(lot_view)
            if reserve_stock and allocated > 0:
                lot = db.get(StockLot, int(allocation["lot_id"]))
                if not lot or lot.company_id != release.company_id:
                    raise ReleaseConflictError("Um lote deixou de estar disponivel durante a reserva")
                lot.reserved = float(lot.reserved or 0) + allocated
                reserved += allocated
        if item["status"] in {"unlinked_material", "unit_mismatch"}:
            status = item["status"]
        elif float(item["shortage_quantity"] or 0) > 1e-9:
            status = "shortage"
        elif reserve_stock:
            status = "reserved"
        else:
            status = "available"
        row = ProductionMaterialRequirement(
            company_id=release.company_id,
            release_id=release.id,
            production_order_id=production_order.id,
            cost_line_id=item["cost_line_id"],
            material_id=item["material_id"],
            description=item["description"],
            material_category=item["material_category"],
            unit=item["unit"],
            unit_required=item["unit_required"],
            required_quantity=item["required_quantity"],
            available_quantity=item["available_quantity"],
            shortage_quantity=item["shortage_quantity"],
            reserved_quantity=_round(reserved, 6),
            average_unit_cost=item["average_unit_cost"],
            real_unit_cost=item["real_unit_cost"],
            estimated_amount=item["estimated_amount"],
            lots=lots,
            status=status,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def release_order_reservations(db: Session, order: ProductionOrder) -> float:
    """Liberta, de forma idempotente, as reservas ainda abertas de uma OF cancelada."""
    released_total = 0.0
    requirements = (
        db.query(ProductionMaterialRequirement)
        .filter_by(production_order_id=order.id)
        .with_for_update()
        .all()
    )
    for requirement in requirements:
        allocations = [dict(item) for item in (requirement.lots or [])]
        released_for_requirement = 0.0
        for allocation in allocations:
            reserved = max(0.0, float(allocation.get("reserved_quantity") or 0))
            if reserved <= 1e-9:
                continue
            lot = (
                db.query(StockLot)
                .filter_by(id=int(allocation.get("lot_id") or 0), company_id=order.company_id)
                .with_for_update()
                .first()
            )
            if not lot:
                raise ReleaseConflictError("Nao foi possivel localizar um lote reservado desta ordem")
            released = min(reserved, max(0.0, float(lot.reserved or 0)))
            lot.reserved = max(0.0, float(lot.reserved or 0) - released)
            allocation["reserved_quantity"] = _round(reserved - released, 6)
            allocation["released_quantity"] = _round(
                float(allocation.get("released_quantity") or 0) + released, 6
            )
            released_for_requirement += released
            released_total += released
        requirement.lots = allocations
        requirement.reserved_quantity = _round(
            max(0.0, float(requirement.reserved_quantity or 0) - released_for_requirement), 6
        )
        requirement.status = "cancelled" if requirement.reserved_quantity <= 1e-9 else "release_error"
    data = dict(order.custom_data or {})
    data["material_status"] = "cancelled"
    data["reservations_released_at"] = datetime.now(timezone.utc).isoformat()
    data["reservations_released_quantity"] = _round(released_total, 6)
    order.custom_data = data
    return _round(released_total, 6)


def release_sheet_to_production(db: Session, sheet_id: int, payload, user_id: int) -> tuple[ProposalProductionRelease, bool]:
    sheet = db.query(CostSheet).filter_by(id=sheet_id).with_for_update().first()
    if not sheet:
        raise ReleaseValidationError("Proposta nao encontrada")
    existing = get_release(db, sheet.id)
    if existing:
        return existing, True
    key = (payload.idempotency_key or "").strip() or f"cost-sheet:{sheet.id}:release"
    reused_key = db.query(ProposalProductionRelease).filter_by(company_id=sheet.company_id, idempotency_key=key).first()
    if reused_key:
        if reused_key.cost_sheet_id == sheet.id:
            return reused_key, True
        raise ReleaseConflictError("A chave de idempotencia ja foi usada noutra proposta")
    if sheet.status not in RELEASABLE_STATUSES:
        raise ReleaseConflictError("O estado da proposta nao permite lancamento")
    lines = db.query(CostLine).filter_by(cost_sheet_id=sheet.id).all()
    if not lines or float(sheet.total_cost or 0) <= 0:
        raise ReleaseValidationError("A proposta precisa de linhas de custo validas")
    if float(sheet.selling_price or 0) <= 0:
        raise ReleaseValidationError("A proposta precisa de preco de venda")
    quantity = float(payload.quantity if payload.quantity is not None else sheet.quantity_basis or 0)
    if quantity <= 0:
        raise ReleaseValidationError("A quantidade tem de ser superior a zero")
    meta = dict(sheet.custom_data or {})
    style = db.get(Style, sheet.style_id)
    if not style or style.company_id != sheet.company_id:
        raise ReleaseValidationError("O artigo da proposta ja nao esta disponivel")
    accepted_customer_id = meta.get("customer_id") or style.customer_id
    if accepted_customer_id and payload.customer_id and payload.customer_id != accepted_customer_id:
        raise ReleaseConflictError(
            "O cliente da proposta aceite nao pode ser alterado no lancamento. Duplique a proposta para criar uma revisao."
        )
    customer_id = accepted_customer_id or payload.customer_id
    customer = db.get(Customer, customer_id) if customer_id else None
    if not customer or customer.company_id != sheet.company_id:
        raise ReleaseValidationError("Escolha um cliente valido antes de lancar a proposta")
    if payload.line_id:
        line = db.get(ProductionLine, payload.line_id)
        if not line or line.company_id != sheet.company_id:
            raise ReleaseValidationError("A linha de producao nao pertence a esta empresa")
    if payload.planned_start and payload.planned_end and payload.planned_end < payload.planned_start:
        raise ReleaseValidationError("A data final planeada nao pode ser anterior ao inicio")

    now = datetime.now(timezone.utc)
    release = ProposalProductionRelease(
        company_id=sheet.company_id,
        cost_sheet_id=sheet.id,
        idempotency_key=key,
        quantity=quantity,
        reserve_stock=payload.reserve_stock,
        released_at=now,
        released_by=user_id,
        request_snapshot=payload.model_dump(mode="json"),
    )
    db.add(release)
    db.flush()

    sales_order_no = _unique_order_no(db, SalesOrder, sheet.company_id, payload.sales_order_no, f"ENC-P{sheet.id:05d}")
    production_order_no = _unique_order_no(db, ProductionOrder, sheet.company_id, payload.order_no, f"OF-P{sheet.id:05d}")
    sales_order = SalesOrder(
        company_id=sheet.company_id,
        customer_id=customer.id,
        order_no=sales_order_no,
        customer_po=payload.customer_po,
        order_date=payload.order_date or date.today(),
        delivery_date=payload.delivery_date,
        status="confirmed",
        custom_data={
            "source": "accepted_cost_proposal", "cost_sheet_id": sheet.id, "release_id": release.id,
            "commercial_name": meta.get("commercial_name"), "commercial_user_id": meta.get("accepted_by") or user_id,
        },
    )
    db.add(sales_order)
    db.flush()
    sales_line = SalesOrderLine(
        company_id=sheet.company_id,
        sales_order_id=sales_order.id,
        style_id=sheet.style_id,
        description=style.description,
        quantity=quantity,
        unit_price=sheet.selling_price,
        delivery_date=payload.delivery_date,
    )
    db.add(sales_line)
    db.flush()
    production_order = ProductionOrder(
        company_id=sheet.company_id,
        sales_order_line_id=sales_line.id,
        style_id=sheet.style_id,
        line_id=payload.line_id,
        order_no=production_order_no,
        quantity=quantity,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        status="planned",
        priority=payload.priority,
        current_stage="planning",
        custom_data={
            "source": "accepted_cost_proposal", "approved_cost_sheet_id": sheet.id,
            "proposal_release_id": release.id, "quote_no": meta.get("quote_no"),
        },
    )
    db.add(production_order)
    db.flush()
    release.sales_order_id = sales_order.id
    release.sales_order_line_id = sales_line.id
    release.production_order_id = production_order.id

    preview = material_requirements_preview(db, sheet, quantity, lock_stock=True)
    persisted = _persist_requirements(db, release, production_order, preview, payload.reserve_stock)
    from .fabric_flow import create_fabric_purchases
    fabric_pos = create_fabric_purchases(db, production_order, persisted)
    from .cutting_map import ensure_cutting_job_for_order
    ensure_cutting_job_for_order(
        db, production_order,
        client=customer.name if customer else None,
        article=style.description if style else None,
    )
    shortage_count = sum(1 for row in persisted if row.shortage_quantity > 1e-9)
    production_data = dict(production_order.custom_data or {})
    production_data.update({
        "material_status": "shortage" if shortage_count else ("reserved" if payload.reserve_stock else "available"),
        "material_shortage_items": shortage_count,
        "cost_snapshot": category_breakdown(db, sheet, quantity),
        "fabric_purchase_orders": [{"id": row.id, "order_no": row.order_no} for row in fabric_pos],
    })
    production_order.custom_data = production_data
    from .order_followup import persist_service_plan, service_plan
    persist_service_plan(production_order, service_plan(db, production_order, [], 0))

    if sheet.status == "draft" or not meta.get("frozen_lines"):
        meta.update({
            "approved_at": meta.get("approved_at") or now.isoformat(),
            "approved_by": meta.get("approved_by") or user_id,
            "frozen_lines": [model_to_dict(row) for row in lines],
        })
    meta.update({
        "customer_id": customer.id,
        "accepted_at": meta.get("accepted_at") or now.isoformat(),
        "accepted_by": meta.get("accepted_by") or user_id,
        "production_order_id": production_order.id,
        "sales_order_id": sales_order.id,
        "proposal_release_id": release.id,
        "released_at": now.isoformat(),
        "released_by": user_id,
        "released_quantity": quantity,
    })
    sheet.custom_data = meta
    sheet.status = "production"
    db.flush()
    return release, False


def release_view(db: Session, release: ProposalProductionRelease, *, already_released: bool = False) -> dict:
    requirements = stored_requirements(db, release)
    production_order = db.get(ProductionOrder, release.production_order_id) if release.production_order_id else None
    sales_order = db.get(SalesOrder, release.sales_order_id) if release.sales_order_id else None
    sheet = db.get(CostSheet, release.cost_sheet_id)
    missing = [row for row in requirements if float(row.get("shortage_quantity") or 0) > 1e-9]
    summary = stock_summary(requirements)
    fabric_pos = (production_order.custom_data or {}).get("fabric_purchase_orders") if production_order else []
    planned_material_total = _round(float(sheet.material_cost or 0) * release.quantity) if sheet else 0.0
    stock_material_total = _round(summary["estimated_material_cost"])
    variance_total = _round(stock_material_total - planned_material_total)
    return {
        "release": model_to_dict(release),
        "already_released": already_released,
        "production_order": model_to_dict(production_order) if production_order else None,
        "sales_order": model_to_dict(sales_order) if sales_order else None,
        "requirements": requirements,
        "shortages": missing,
        "fabric_purchase_orders": fabric_pos or [],
        "stock_summary": summary,
        "cost_variance": {
            "planned_material_unit_cost": _round(sheet.material_cost) if sheet else 0.0,
            "stock_material_unit_cost": _round(stock_material_total / release.quantity) if release.quantity else 0.0,
            "unit_variance": _round((stock_material_total / release.quantity if release.quantity else 0) - (sheet.material_cost if sheet else 0)),
            "planned_material_total": planned_material_total,
            "stock_material_total": stock_material_total,
            "total_variance": variance_total,
            "variance_pct": round(variance_total / planned_material_total * 100, 2) if planned_material_total else (100.0 if stock_material_total else 0.0),
        },
        "category_breakdown": category_breakdown(db, sheet, release.quantity) if sheet else {},
    }
