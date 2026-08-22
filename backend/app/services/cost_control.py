from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func

from ..models import (
    ActualCostEntry, BOMItem, Company, CostLine, CostSheet, Customer, CuttingJob, InventoryMovement,
    Machine, Material, OverheadCost, ProductionEvent, ProductionLine, ProductionOrder, SalesOrder,
    SalesOrderLine, StockLot, Style, SubcontractJob, SubcontractService,
)
from .costing import recalculate_sheet
from .currency import base_currency, convert_to_base
from .proposal_release import ACCEPTED_STATUSES, annotated_cost_lines, production_preview
from .serialization import model_to_dict


CATEGORIES = ("material", "labor", "machine", "subcontract", "overhead", "energy", "packaging", "transport", "other")
# Nota: a CostSheet só tem colunas fixas para as 6 categorias originais; as 3
# novas (energy/packaging/transport) ganham linha própria aqui no custo real
# (actual_order_cost/order_control) mas continuam a cair em "other_cost" no
# resumo da ficha (costing.py::recalculate_sheet), sem migração de esquema.
OUTGOING_COST = {"issue", "consume", "adjustment_out"}
RETURN_COST = {"return", "adjustment_in"}


def _round(value):
    return round(float(value or 0), 4)


def sheet_view(db, sheet: CostSheet) -> dict:
    style = db.get(Style, sheet.style_id)
    meta = sheet.custom_data or {}
    customer_id = meta.get("customer_id") or (style.customer_id if style else None)
    candidate_customer = db.get(Customer, customer_id) if customer_id else None
    customer = candidate_customer if candidate_customer and candidate_customer.company_id == sheet.company_id else None
    lines = annotated_cost_lines(db, sheet)
    preview = production_preview(db, sheet)
    result = model_to_dict(sheet)
    company = db.get(Company, sheet.company_id)
    sheet_currency = sheet.currency or base_currency(company)
    sales_total_native = _round(sheet.selling_price * sheet.quantity_basis)
    proposal_total_native = _round(sheet.total_cost * sheet.quantity_basis)
    margin_native = _round((sheet.selling_price - sheet.total_cost) * sheet.quantity_basis)
    fx = convert_to_base(db, company, sales_total_native, sheet_currency)
    fx_cost = convert_to_base(db, company, proposal_total_native, sheet_currency)
    fx_margin = convert_to_base(db, company, margin_native, sheet_currency)
    result.update({
        "currency": sheet_currency,
        "base_currency": base_currency(company),
        "fx_missing": fx["fx_missing"],
        "fx_rate": fx["rate"],
        "sales_total_base": fx["amount"],
        "proposal_total_base": fx_cost["amount"],
        "margin_value_base": fx_margin["amount"],
        "quote_no": meta.get("quote_no") or f"PROP-{sheet.id:05d}",
        "customer_id": customer.id if customer else None,
        "customer_name": customer.name if customer else "—",
        "customer_email": customer.email if customer else None,
        "valid_until": meta.get("valid_until"),
        "notes": meta.get("notes"),
        "client_notes": meta.get("client_notes") or "",
        "vat_pct": float(meta.get("vat_pct") or 23),
        "payment_terms": meta.get("payment_terms") or "30 dias",
        "commercial_name": meta.get("commercial_name"),
        "approved_at": meta.get("approved_at"),
        "accepted_at": meta.get("accepted_at"),
        "style_reference": style.reference if style else str(sheet.style_id),
        "style_description": style.description if style else "",
        "style_image_url": style.image_url if style else None,
        "proposal_total": _round(sheet.total_cost * sheet.quantity_basis),
        "sales_total": _round(sheet.selling_price * sheet.quantity_basis),
        "vat_amount": _round(sheet.selling_price * sheet.quantity_basis * float(meta.get("vat_pct") or 23) / 100),
        "sales_total_vat": _round(sheet.selling_price * sheet.quantity_basis * (1 + float(meta.get("vat_pct") or 23) / 100)),
        "margin_value": _round((sheet.selling_price - sheet.total_cost) * sheet.quantity_basis),
        "line_count": len(lines),
        "category_breakdown": preview["category_breakdown"],
        "stock_summary": preview["stock_summary"],
        "requirements": preview["requirements"],
        "cost_variance": preview["cost_variance"],
        "production_order_id": preview["production_order_id"],
        "sales_order_id": meta.get("sales_order_id"),
        "released_quantity": meta.get("released_quantity"),
        "released_at": preview["released_at"],
        "release_ready": preview["can_release"],
        "release_blockers": preview["blockers"],
        "release_warnings": preview["warnings"],
        "already_released": preview["already_released"],
    })
    return {
        "sheet": result,
        "lines": lines,
        "category_breakdown": preview["category_breakdown"],
        "stock_summary": preview["stock_summary"],
        "requirements": preview["requirements"],
        "cost_variance": preview["cost_variance"],
    }


def list_sheets(db, company_id: int) -> list[dict]:
    rows = db.query(CostSheet).filter_by(company_id=company_id).order_by(CostSheet.updated_at.desc()).all()
    result = []
    for row in rows:
        summary = sheet_view(db, row)["sheet"]
        summary.pop("requirements", None)
        summary["custom_data"] = {
            key: value for key, value in (summary.get("custom_data") or {}).items()
            if key not in {"frozen_lines", "visuals"}
        }
        result.append(summary)
    return result


def save_sheet(db, sheet: CostSheet, payload) -> CostSheet:
    if sheet.status != "draft":
        raise ValueError("Uma proposta aprovada fica congelada. Duplique-a para criar uma revisão.")
    if payload.customer_id:
        customer = db.get(Customer, payload.customer_id)
        if not customer or customer.company_id != sheet.company_id:
            raise ValueError("O cliente nao pertence a esta empresa")
    meta = dict(sheet.custom_data or {})
    meta.update({
        "customer_id": payload.customer_id,
        "quote_no": (payload.quote_no or meta.get("quote_no") or f"PROP-{sheet.id:05d}").strip(),
        "valid_until": payload.valid_until.isoformat() if payload.valid_until else None,
        "notes": payload.notes,
        "client_notes": getattr(payload, "client_notes", None) if getattr(payload, "client_notes", None) is not None else meta.get("client_notes"),
        "vat_pct": float(getattr(payload, "vat_pct", None) or meta.get("vat_pct") or 23),
        "payment_terms": (getattr(payload, "payment_terms", None) or meta.get("payment_terms") or "30 dias"),
        "cost_source": "entered_and_verified",
    })
    sheet.custom_data = meta
    sheet.quantity_basis = payload.quantity
    sheet.selling_price = payload.selling_price
    currency = (getattr(payload, "currency", None) or "").strip().upper()
    if currency:
        sheet.currency = currency
    db.query(CostLine).filter_by(cost_sheet_id=sheet.id).delete(synchronize_session=False)
    for item in payload.lines:
        category = item.category if item.category in CATEGORIES else "other"
        db.add(CostLine(
            company_id=sheet.company_id,
            cost_sheet_id=sheet.id,
            category=category,
            description=item.description.strip(),
            quantity=item.quantity,
            unit=item.unit.strip(),
            unit_cost=item.unit_cost,
            amount=_round(item.quantity * item.unit_cost),
            source_type=item.source_type or "manual_verified",
            source_id=item.source_id,
        ))
    db.flush()
    return recalculate_sheet(db, sheet)


def approved_baseline(db, order: ProductionOrder) -> CostSheet | None:
    linked_id = (order.custom_data or {}).get("approved_cost_sheet_id")
    if linked_id:
        linked = db.get(CostSheet, linked_id)
        if linked and linked.status in ACCEPTED_STATUSES and linked.company_id == order.company_id:
            return linked
    customer_id = None
    if order.sales_order_line_id:
        sales_line = db.get(SalesOrderLine, order.sales_order_line_id)
        sales_order = db.get(SalesOrder, sales_line.sales_order_id) if sales_line else None
        customer_id = sales_order.customer_id if sales_order else None
    sheets = db.query(CostSheet).filter(
        CostSheet.company_id == order.company_id,
        CostSheet.style_id == order.style_id,
        CostSheet.status.in_(ACCEPTED_STATUSES),
    ).order_by(CostSheet.version.desc()).all()
    if customer_id:
        exact = [row for row in sheets if (row.custom_data or {}).get("customer_id") == customer_id]
        if exact:
            return exact[0]
    return sheets[0] if sheets else None


def _department_line_ids(db, company_id: int, department_id: int | None) -> set[int] | None:
    """None = sem filtro (todas). Conjunto vazio = filtro ativo mas nada corresponde."""
    if not department_id:
        return None
    return {row.id for row in db.query(ProductionLine.id).filter_by(company_id=company_id, department_id=department_id).all()}


def _department_machine_ids(db, company_id: int, department_id: int | None) -> set[int] | None:
    if not department_id:
        return None
    return {row.id for row in db.query(Machine.id).filter_by(company_id=company_id, department_id=department_id).all()}


def _basis_metric(db, company_id: int | None, order_id: int | None, basis: str, department_id: int | None, start, end) -> float:
    """Metrica de rateio para UM lado (a OF ou a empresa toda) no periodo do custo geral.

    company_id filtra por empresa (lado "empresa"); order_id filtra por OF (lado
    "OF"). Um dos dois vem None consoante o lado a calcular.
    """
    line_filter = _department_line_ids(db, company_id, department_id) if company_id else None
    machine_filter = _department_machine_ids(db, company_id, department_id) if company_id else None

    def event_query():
        q = db.query(ProductionEvent).filter(ProductionEvent.event_time >= start, ProductionEvent.event_time < end)
        q = q.filter(ProductionEvent.production_order_id == order_id) if order_id else q.filter(ProductionEvent.company_id == company_id)
        if line_filter is not None:
            q = q.filter(ProductionEvent.line_id.in_(line_filter))
        return q

    def cutting_query():
        q = db.query(CuttingJob).filter(CuttingJob.created_at >= start, CuttingJob.created_at < end)
        q = q.filter(CuttingJob.production_order_id == order_id) if order_id else q.filter(CuttingJob.company_id == company_id)
        if machine_filter is not None:
            q = q.filter(CuttingJob.machine_id.in_(machine_filter))
        return q

    if basis == "units":
        return sum(row.quantity_good or 0 for row in event_query().all())
    if basis == "labor_hours":
        return sum((row.duration_minutes or 0) for row in event_query().filter(ProductionEvent.employee_id.isnot(None)).all()) / 60
    if basis == "machine_hours":
        machine_minutes = sum((row.duration_minutes or 0) for row in event_query().filter(ProductionEvent.machine_id.isnot(None)).all())
        machine_minutes += sum((row.duration_minutes or 0) for row in cutting_query().filter(CuttingJob.machine_id.isnot(None)).all())
        return machine_minutes / 60
    if basis == "revenue":
        total = 0.0
        for row in event_query().all():
            order = db.get(ProductionOrder, row.production_order_id)
            baseline = approved_baseline(db, order) if order else None
            total += (row.quantity_good or 0) * (baseline.selling_price if baseline else 0)
        return total
    # production_minutes (default e fallback)
    return sum(row.duration_minutes or 0 for row in event_query().all()) + sum(row.duration_minutes or 0 for row in cutting_query().all())


def _overhead_allocation(db, order: ProductionOrder) -> tuple[float, list[dict]]:
    entries = []
    total = 0.0
    basis_label = {
        "production_minutes": "minutos de produção", "units": "unidades produzidas",
        "labor_hours": "horas de mão de obra", "machine_hours": "horas de máquina", "revenue": "receita",
    }
    for overhead in db.query(OverheadCost).filter_by(company_id=order.company_id).all():
        start = datetime.combine(overhead.period_start, time.min, tzinfo=timezone.utc)
        end = datetime.combine(overhead.period_end + timedelta(days=1), time.min, tzinfo=timezone.utc)
        basis = overhead.allocation_basis if overhead.allocation_basis in basis_label else "production_minutes"
        order_metric = _basis_metric(db, None, order.id, basis, overhead.department_id, start, end)
        if not order_metric:
            continue
        company_metric = _basis_metric(db, order.company_id, None, basis, overhead.department_id, start, end)
        if not company_metric:
            continue
        amount = _round(overhead.amount * min(1, order_metric / company_metric))
        if amount:
            total += amount
            entries.append({
                "category": "overhead", "description": overhead.description,
                "amount": amount, "source": "rateio_real",
                "reference": f"{overhead.period_start} a {overhead.period_end} · rateio por {basis_label[basis]}"
                + (" · departamento" if overhead.department_id else ""),
            })
    return _round(total), entries


def actual_order_cost(db, order: ProductionOrder) -> dict:
    totals = defaultdict(float)
    details = []
    movement_rows = db.query(InventoryMovement, StockLot, Material).join(
        StockLot, StockLot.id == InventoryMovement.stock_lot_id
    ).join(Material, Material.id == StockLot.material_id).filter(
        InventoryMovement.production_order_id == order.id
    ).all()
    for movement, lot, material in movement_rows:
        if movement.movement_type in OUTGOING_COST:
            amount = abs(movement.quantity or 0) * (movement.unit_cost or 0)
        elif movement.movement_type in RETURN_COST:
            amount = -abs(movement.quantity or 0) * (movement.unit_cost or 0)
        else:
            continue
        amount = _round(amount)
        totals["material"] += amount
        details.append({
            "category": "material", "description": material.name, "amount": amount,
            "source": "stock", "reference": movement.reference or lot.lot_no,
            "material_id": material.id, "quantity": -abs(movement.quantity or 0) if amount < 0 else abs(movement.quantity or 0),
            "unit": material.unit, "unit_cost": movement.unit_cost,
        })

    events = db.query(ProductionEvent).filter_by(production_order_id=order.id).all()
    event_labor = _round(sum(row.labor_cost or 0 for row in events))
    event_machine = _round(sum(row.machine_cost or 0 for row in events))
    cutting = db.query(CuttingJob).filter_by(production_order_id=order.id).all()
    cutting_labor = _round(sum(row.labor_cost or 0 for row in cutting))
    cutting_machine = _round(sum(row.machine_cost or 0 for row in cutting))
    for category, description, amount, source in [
        ("labor", "Mão de obra registada na produção", event_labor, "terminal_producao"),
        ("machine", "Máquinas registadas na produção", event_machine, "terminal_producao"),
        ("labor", "Mão de obra do corte", cutting_labor, "corte"),
        ("machine", "Máquinas do corte", cutting_machine, "corte"),
    ]:
        if amount:
            totals[category] += amount
            details.append({"category": category, "description": description, "amount": amount, "source": source, "reference": None})

    subcontract_jobs = db.query(SubcontractJob).filter(
        SubcontractJob.production_order_id == order.id,
        SubcontractJob.status != "cancelled",
        SubcontractJob.actual_cost > 0,
    ).all()
    for job in subcontract_jobs:
        service = db.get(SubcontractService, job.subcontract_service_id)
        amount = _round(job.actual_cost)
        totals["subcontract"] += amount
        details.append({
            "category": "subcontract",
            "description": service.name if service else job.reference,
            "amount": amount,
            "source": "subcontrato_recebido",
            "reference": job.reference,
        })

    manual = db.query(ActualCostEntry).filter_by(production_order_id=order.id).order_by(ActualCostEntry.occurred_on.desc()).all()
    for entry in manual:
        totals[entry.category] += entry.amount
        details.append({
            **model_to_dict(entry), "source": "documento_real", "reference": entry.reference,
        })

    overhead, overhead_lines = _overhead_allocation(db, order)
    totals["overhead"] += overhead
    details.extend(overhead_lines)
    return {"totals": {key: _round(totals[key]) for key in CATEGORIES}, "details": details}


def order_control(db, order: ProductionOrder) -> dict:
    style = db.get(Style, order.style_id)
    baseline = approved_baseline(db, order)
    actual = actual_order_cost(db, order)
    actual_total = _round(sum(actual["totals"].values()))
    completed = max(0, order.completed_quantity or 0)
    if not baseline:
        return {
            "order": {**model_to_dict(order), "style_reference": style.reference if style else "—", "style_description": style.description if style else ""},
            "baseline": None, "actual": actual, "metrics": {"actual_total": actual_total}, "comparison": [],
        }
    lines = db.query(CostLine).filter_by(cost_sheet_id=baseline.id).all()
    # O custo real (actual_order_cost) e sempre incorrido na moeda da empresa
    # (mao de obra/maquina/material locais); o orcamento vem da ficha de custo,
    # que pode ter sido cotada noutra moeda. Converte o orcamento para a moeda
    # da empresa antes de comparar - senao a comparacao mistura moedas.
    company = db.get(Company, order.company_id)
    fx = convert_to_base(db, company, 1, baseline.currency)
    fx_rate = fx["rate"] if not fx["fx_missing"] else 1.0
    budget_unit = defaultdict(float)
    for line in lines:
        budget_unit[line.category if line.category in CATEGORIES else "other"] += (line.amount or 0) * fx_rate
    baseline_unit_cost = baseline.total_cost * fx_rate
    earned_budget = _round(baseline_unit_cost * completed)
    full_budget = _round(baseline_unit_cost * order.quantity)
    actual_unit = _round(actual_total / completed) if completed else 0
    deviation = _round(actual_total - earned_budget)
    deviation_pct = round(deviation / earned_budget * 100, 2) if earned_budget else (100 if actual_total else 0)
    # Previsao do custo final (EAC): com produção suficiente para o custo real
    # observado ser fiável (>=10% da OF), extrapola o que falta a esse ritmo em
    # vez de assumir que o resto vai custar exatamente o orçamento-padrão.
    remaining_qty = max(0, (order.quantity or 0) - completed)
    progress_ratio = completed / order.quantity if order.quantity else 0
    remaining_unit_cost = actual_unit if progress_ratio >= 0.1 and actual_unit else baseline_unit_cost
    forecast_total = _round(actual_total + remaining_qty * remaining_unit_cost)
    comparison = []
    for category in CATEGORIES:
        allowed = _round(budget_unit[category] * completed)
        used = _round(actual["totals"][category])
        difference = _round(used - allowed)
        comparison.append({
            "category": category, "budget_unit": _round(budget_unit[category]),
            "budget_to_date": allowed, "actual": used, "deviation": difference,
            "deviation_pct": round(difference / allowed * 100, 2) if allowed else (100 if used else 0),
        })
    material_comparison = []
    actual_materials = defaultdict(lambda: {"quantity": 0.0, "amount": 0.0})
    for detail in actual["details"]:
        if detail.get("source") == "stock" and detail.get("material_id"):
            actual_materials[detail["material_id"]]["quantity"] += detail.get("quantity", 0)
            actual_materials[detail["material_id"]]["amount"] += detail.get("amount", 0)
    for line in lines:
        if line.category != "material" or line.source_type not in {"wizard_material", "wizard_accessory", "bom"} or not line.source_id:
            continue
        material_id = line.source_id
        if line.source_type == "bom":
            bom_item = db.get(BOMItem, line.source_id)
            material_id = bom_item.material_id if bom_item else None
        if not material_id:
            continue
        actual_item = actual_materials[material_id]
        planned_quantity = _round(line.quantity * completed)
        material_comparison.append({
            "material_id": material_id, "description": line.description, "unit": line.unit,
            "planned_quantity": planned_quantity, "actual_quantity": _round(actual_item["quantity"]),
            "quantity_deviation": _round(actual_item["quantity"] - planned_quantity),
            "planned_cost": _round(line.amount * fx_rate * completed), "actual_cost": _round(actual_item["amount"]),
            "cost_deviation": _round(actual_item["amount"] - line.amount * fx_rate * completed),
        })
    status = "risk" if deviation_pct > 5 else "warning" if deviation_pct > 0 else "on_track"
    return {
        "order": {**model_to_dict(order), "style_reference": style.reference if style else "—", "style_description": style.description if style else ""},
        "baseline": sheet_view(db, baseline)["sheet"],
        "actual": actual,
        "metrics": {
            "completed_quantity": completed, "progress_pct": round(completed / order.quantity * 100, 2) if order.quantity else 0,
            "budget_unit": _round(baseline_unit_cost), "budget_total": full_budget,
            "earned_budget": earned_budget, "actual_total": actual_total, "actual_unit": actual_unit,
            "deviation": deviation, "deviation_pct": deviation_pct, "forecast_total": forecast_total, "status": status,
            "baseline_currency": baseline.currency or base_currency(company), "fx_rate": fx["rate"], "fx_missing": fx["fx_missing"],
        },
        "comparison": comparison,
        "material_comparison": material_comparison,
    }
