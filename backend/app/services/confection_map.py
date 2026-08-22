from __future__ import annotations

import json
from datetime import date, timedelta
from math import ceil

from sqlalchemy.orm import Session

from ..models import Customer, Department, ProductionLine, ProductionOrder, SalesOrder, SalesOrderLine, SewingPlan, Style, SubcontractJob, SubcontractService, Supplier
from .confection_schedule import (
    LINE_CATALOG, apply_extra_hours, audit_message, build_board, duration_days, end_from_start,
    first_fit, heijunka_consult, insert_and_push, line_hours_per_day, monday_of, next_workday,
    order_hours, shift_block, simulate_accept, workdays_between, add_workdays,
)
from .fabric_flow import assert_sewing_ready, fabric_status_map
from .production_stage import update_order_stage


MAP_NOTE = "pmap"
LINE_COLORS = ("green", "blue", "teal", "orange")
FOLD_LINE_KEYS = {"A": "L1", "LA": "L1", "B": "L2", "LB": "L2", "C": "L2", "LC": "L2"}
LEGACY_LINE_KEYS = {row["key"]: row["code"] for row in LINE_CATALOG}


def company_line_catalog(db: Session, company_id: int) -> list[dict]:
    lines = db.query(ProductionLine).filter_by(company_id=company_id, active=True).order_by(ProductionLine.id).all()
    departments = {row.id: row for row in db.query(Department).filter_by(company_id=company_id).all()}
    sewing = []
    for row in lines:
        department = departments.get(row.department_id)
        code = (department.code if department else "") or ""
        name = (department.name if department else "") or ""
        if code == "CONF" or "confe" in name.lower():
            sewing.append(row)
    catalog = []
    for index, row in enumerate(sewing):
        hours_day = max(8.0, (row.capacity_minutes_day or 480) / 60)
        catalog.append({
            "key": row.code,
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "family": "",
            "posts": "",
            "pcs_hour": row.target_pcs_hour or 0,
            "color": LINE_COLORS[index % len(LINE_COLORS)],
            "hours_day": hours_day,
        })
    return catalog


def _line_maps(db: Session, company_id: int) -> tuple[dict, dict, list[dict]]:
    catalog = company_line_catalog(db, company_id)
    lines = db.query(ProductionLine).filter_by(company_id=company_id).all()
    models = {row.code: row for row in lines}
    by_id = {row.id: row.code for row in lines}
    return models, by_id, catalog


def _meta(plan: SewingPlan) -> dict:
    try:
        data = json.loads(plan.notes or "")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _as_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _write_meta(plan: SewingPlan, **fields):
    meta = _meta(plan)
    meta[MAP_NOTE] = True
    meta.update({key: value for key, value in fields.items() if value is not None})
    plan.notes = json.dumps(meta, ensure_ascii=False)


def _fold_line_key(line_key: str | None, catalog: list[dict]) -> str:
    mapped = FOLD_LINE_KEYS.get(line_key or "", LEGACY_LINE_KEYS.get(line_key or "", line_key or ""))
    keys = [row["key"] for row in catalog]
    if mapped in keys:
        return mapped
    return keys[0] if keys else mapped or "L1"


def _resolve_line_key(plan: SewingPlan, by_id: dict, meta: dict, catalog: list[dict]) -> str:
    if plan.line_id and by_id.get(plan.line_id):
        return _fold_line_key(by_id[plan.line_id], catalog)
    return _fold_line_key(meta.get("line_key"), catalog)


def _canon_line_key(line_key: str | None, catalog: list[dict]) -> str:
    return _fold_line_key(line_key, catalog)


def _place(items: list[dict], new_item: dict, extra_hours: bool, catalog: list[dict]) -> dict:
    placed = first_fit(items, new_item, extra_hours, date.today())
    placed["line_key"] = _canon_line_key(placed.get("line_key"), catalog)
    return placed


def _line_for_key(models: dict, catalog: list[dict], line_key: str):
    code = _fold_line_key(line_key, catalog)
    if code in models:
        return models[code]
    if catalog:
        return models.get(catalog[0]["key"])
    return None


def _ensure_customer(db: Session, company_id: int, name: str) -> Customer:
    existing = db.query(Customer).filter(Customer.company_id == company_id, Customer.name.ilike(name)).first()
    if existing:
        return existing
    code = "".join(ch for ch in name.upper() if ch.isalnum())[:12] or "CLI"
    customer = Customer(company_id=company_id, code=f"{code}-{company_id}", name=name, payment_terms="30 dias")
    db.add(customer)
    db.flush()
    return customer


def _default_style(db: Session, company_id: int, article: str):
    style = db.query(Style).filter(Style.company_id == company_id, Style.description == article).first()
    if style:
        return style
    any_style = db.query(Style).filter_by(company_id=company_id).first()
    if any_style:
        return any_style
    style = Style(company_id=company_id, reference=article[:20], description=article, lifecycle_status="approved")
    db.add(style)
    db.flush()
    return style


def _next_op_code(db: Session, company_id: int) -> str:
    rows = db.query(ProductionOrder.order_no).filter(
        ProductionOrder.company_id == company_id, ProductionOrder.order_no.like("OP-2026-%")
    ).all()
    numbers = []
    for (order_no,) in rows:
        try:
            numbers.append(int(str(order_no).split("-")[-1]))
        except ValueError:
            continue
    nxt = max(numbers) + 1 if numbers else 900
    return f"OP-2026-{nxt:04d}"


def load_items(db: Session, company_id: int) -> list[dict]:
    _, by_id, catalog = _line_maps(db, company_id)
    plans = db.query(SewingPlan).filter(
        SewingPlan.company_id == company_id,
        SewingPlan.status.notin_(["completed", "cancelled"]),
    ).all()
    items = []
    for plan in plans:
        meta = _meta(plan)
        if not meta.get(MAP_NOTE) and plan.line_id not in by_id and plan.status != "backlog":
            continue
        order = db.get(ProductionOrder, plan.production_order_id) if plan.production_order_id else None
        style = db.get(Style, plan.style_id) if plan.style_id else None
        customer = None
        sales = None
        if order and order.sales_order_line_id:
            line = db.get(SalesOrderLine, order.sales_order_line_id)
            sales = db.get(SalesOrder, line.sales_order_id) if line else None
            customer = db.get(Customer, sales.customer_id) if sales else None
        line_key = _resolve_line_key(plan, by_id, meta, catalog)
        hours = _item_hours(plan.quantity, plan.sam_minutes)
        hours_day = _hours_day(catalog, line_key, False)
        work_days = _work_days_from(plan, meta)
        needed = _days_needed(hours, hours_day)
        supplier = db.get(Supplier, plan.supplier_id) if plan.supplier_id else None
        promised = None
        if sales and sales.delivery_date:
            promised = sales.delivery_date
        elif order and order.planned_end:
            promised = order.planned_end
        items.append({
            "id": plan.id,
            "code": (order.order_no if order else plan.code),
            "order_id": order.id if order else None,
            "client": meta.get("client") or (customer.name if customer else "Cliente"),
            "article": meta.get("article") or (style.description if style else plan.code),
            "quantity": plan.quantity,
            "sam_minutes": plan.sam_minutes,
            "hours": hours,
            "hours_day": hours_day,
            "days_needed": needed,
            "work_days": work_days,
            "day_share": _day_shares(meta, work_days, hours, hours_day),
            "days_planned": len(work_days),
            "days_left": max(0, needed - len(work_days)),
            "source_type": plan.source_type or "confirmed",
            "line_key": None if plan.allocation_type == "external" else line_key,
            "status": "backlog" if plan.status == "backlog" or (plan.allocation_type != "external" and not work_days) else plan.status,
            "urgent": bool(meta.get("urgent") or plan.priority == 1),
            "start_date": None if plan.status == "backlog" or (plan.allocation_type != "external" and not work_days) else (work_days[0] if work_days else plan.start_date.isoformat()),
            "end_date": work_days[-1] if work_days else (plan.end_date.isoformat() if plan.end_date else None),
            "start_fraction": 0,
            "promised_date": promised.isoformat() if promised else None,
            "due_in_days": (promised - date.today()).days if promised else None,
            "allocation_type": plan.allocation_type,
            "supplier_id": plan.supplier_id,
            "supplier_name": supplier.name if supplier else None,
            "notes": plan.notes,
        })
    statuses = fabric_status_map(db, company_id, [row["order_id"] for row in items])
    for row in items:
        status = statuses.get(row["order_id"]) or {"ready": True, "label": "Sem malha na ficha", "needed": 0, "unit": "kg"}
        row["fabric_ready"] = status["ready"]
        row["fabric_label"] = status["label"]
        row["fabric_needed"] = status["needed"]
        row["fabric_unit"] = status["unit"]
    return items


def _persist_item(db: Session, company_id: int, item: dict, extra_hours: bool):
    models, _, catalog = _line_maps(db, company_id)
    line = _line_for_key(models, catalog, item.get("line_key") or "")
    plan = db.get(SewingPlan, item["id"]) if item.get("id") else None
    hours = order_hours(item["quantity"], item["sam_minutes"])
    hours_day = line_hours_per_day(extra_hours)
    duration = duration_days(hours, hours_day)
    start = next_workday(_as_date(item["start_date"])) if item.get("start_date") and item.get("status") != "backlog" else date.today()
    end, _ = end_from_start(start, duration, item.get("start_fraction") or 0, monday_of(start))
    if not plan:
        return
    plan.line_id = line.id if line and item.get("status") != "backlog" else None
    plan.start_date = start
    plan.end_date = end
    plan.quantity = item["quantity"]
    plan.sam_minutes = item["sam_minutes"]
    plan.required_minutes = round(hours * 60, 2)
    plan.status = item.get("status") or "planned"
    plan.allocation_type = "internal"
    if item.get("urgent"):
        plan.priority = 1
    _write_meta(plan, client=item.get("client"), article=item.get("article"), sf=item.get("start_fraction") or 0,
                urgent=item.get("urgent"), line_key=item.get("line_key"))
    if plan.production_order_id:
        order = db.get(ProductionOrder, plan.production_order_id)
        if order:
            order.line_id = plan.line_id
            order.planned_start = plan.start_date if plan.status != "backlog" else order.planned_start
            order.planned_end = plan.end_date if plan.status != "backlog" else order.planned_end
            if plan.status == "backlog":
                order.current_stage = "backlog"
            elif item.get("urgent"):
                order.current_stage = "urgente"
            else:
                order.current_stage = "confeção"


def persist_items(db: Session, company_id: int, items: list[dict], extra_hours: bool):
    for item in items:
        if item.get("id"):
            _persist_item(db, company_id, item, extra_hours)
    db.flush()


def _hours_day(catalog: list[dict], line_key: str | None, extra_hours: bool) -> float:
    line = next((row for row in catalog if row["key"] == line_key), None)
    base = (line or {}).get("hours_day") or line_hours_per_day(False)
    return base * 1.25 if extra_hours else base


def _item_hours(quantity, sam) -> float:
    return round(order_hours(quantity or 0, sam or 0), 1)


def _days_needed(hours: float, hours_day: float) -> int:
    if hours_day <= 0:
        return 1
    return max(1, ceil(hours / hours_day)) if hours else 1


def _work_days_from(plan: SewingPlan, meta: dict) -> list[str]:
    stored = meta.get("work_days")
    if isinstance(stored, list) and stored:
        return sorted({str(day)[:10] for day in stored if day})
    if plan.status == "backlog" or not plan.start_date:
        return []
    end = plan.end_date or plan.start_date
    return [day.isoformat() for day in workdays_between(plan.start_date, end)]


def _day_shares(meta: dict, work_days: list[str], hours: float, hours_day: float) -> dict:
    stored = meta.get("day_share") if isinstance(meta.get("day_share"), dict) else {}
    if work_days and any(float(stored.get(day) or 0) for day in work_days):
        return {day: round(float(stored.get(day) or 0), 1) for day in work_days}
    shares = {}
    remaining = 100.0
    chunk = min(100.0, (hours_day / hours * 100) if hours else 0)
    for day in work_days:
        take = min(chunk, remaining)
        shares[day] = round(take, 1)
        remaining = round(remaining - take, 1)
    return shares


def _occupied(items: list[dict], line_key: str, exclude_id=None) -> set[str]:
    busy = set()
    for row in items:
        if row.get("id") == exclude_id or row.get("allocation_type") == "external":
            continue
        if row.get("line_key") != line_key:
            continue
        busy.update(row.get("work_days") or [])
    return busy


def _next_free_days(items: list[dict], line_key: str, count: int, exclude_id=None) -> list[str]:
    busy = _occupied(items, line_key, exclude_id)
    found = []
    cursor = next_workday(date.today())
    guard = 0
    while len(found) < max(1, count) and guard < 400:
        key = cursor.isoformat()
        if key not in busy:
            found.append(key)
        cursor = next_workday(cursor + timedelta(days=1))
        guard += 1
    return found


def _save_schedule(db: Session, plan: SewingPlan, *, line, supplier, work_days: list[str], extra_hours: bool, catalog, item: dict):
    hours = _item_hours(plan.quantity, plan.sam_minutes)
    hours_day = _hours_day(catalog, item.get("line_key"), extra_hours)
    plan.required_minutes = round(hours * 60, 2)
    work_days = sorted({str(day)[:10] for day in work_days if day})
    if supplier:
        plan.allocation_type = "external"
        plan.supplier_id = supplier.id
        plan.line_id = None
        plan.status = "planned"
        plan.start_date = date.today()
        plan.end_date = date.today() + timedelta(days=supplier.lead_time_days or 7)
        work_days = []
    elif work_days:
        plan.allocation_type = "internal"
        plan.supplier_id = None
        plan.line_id = line.id if line else None
        plan.status = "planned"
        plan.start_date = date.fromisoformat(work_days[0])
        plan.end_date = date.fromisoformat(work_days[-1])
    else:
        plan.allocation_type = "internal"
        plan.supplier_id = None
        plan.line_id = None
        plan.status = "backlog"
        plan.start_date = date.today()
        plan.end_date = date.today()
    _write_meta(
        plan,
        client=item.get("client"),
        article=item.get("article"),
        line_key=item.get("line_key"),
        work_days=work_days,
        day_share=_day_shares({"day_share": item.get("day_share")}, work_days, hours, hours_day) if work_days else {},
        days_needed=_days_needed(hours, hours_day),
    )
    if plan.production_order_id:
        order = db.get(ProductionOrder, plan.production_order_id)
        if order:
            order.line_id = plan.line_id
            if plan.status != "backlog":
                order.planned_start = plan.start_date
                order.planned_end = plan.end_date
                order.current_stage = "confeção externa" if plan.allocation_type == "external" else "confeção"
            else:
                order.current_stage = "backlog"


def production_map(db: Session, company_id: int, extra_hours: bool = False, weeks: int = 12) -> dict:
    items = load_items(db, company_id)
    _, _, catalog = _line_maps(db, company_id)
    board = build_board(items, date.today(), extra_hours=extra_hours, weeks=weeks, catalog=catalog or None)
    board["styles"] = [
        {"id": row.id, "reference": row.reference, "description": row.description}
        for row in db.query(Style).filter_by(company_id=company_id).order_by(Style.reference).all()
    ]
    board["contractors"] = [
        {
            "id": row.id, "name": row.name, "weekly_capacity": row.weekly_capacity or 0,
            "piece_cost": row.piece_cost or 0, "lead_time_days": row.lead_time_days or 0,
        }
        for row in db.query(Supplier).filter_by(company_id=company_id, supplier_type="sewing", active=True).order_by(Supplier.name).all()
    ]
    return board


def _create_order_plan(db: Session, company_id: int, payload: dict, status: str, extra_hours: bool) -> SewingPlan:
    models, _, catalog = _line_maps(db, company_id)
    line = _line_for_key(models, catalog, payload.get("line_key") or "")
    article = payload.get("article") or "Artigo"
    client_name = payload.get("client") or "Cliente"
    customer = _ensure_customer(db, company_id, client_name)
    style = db.get(Style, payload["style_id"]) if payload.get("style_id") else _default_style(db, company_id, article)
    if payload.get("style_id") and style:
        article = style.description or article
    quantity = float(payload.get("quantity") or 0)
    sam = float(payload.get("sam_minutes") or 0)
    hours = order_hours(quantity, sam)
    duration = duration_days(hours, line_hours_per_day(extra_hours))
    start = next_workday(_as_date(payload.get("start_date"))) if payload.get("start_date") and status != "backlog" else date.today()
    end, _ = end_from_start(start, duration, 0, monday_of(start))
    order_no = payload.get("code") or _next_op_code(db, company_id)
    promised = _as_date(payload.get("promised_date")) or end
    sales = SalesOrder(
        company_id=company_id, customer_id=customer.id, order_no=f"EC-{order_no}",
        order_date=date.today(), delivery_date=promised,
        status="confirmed",
    )
    db.add(sales)
    db.flush()
    sales_line = SalesOrderLine(
        company_id=company_id, sales_order_id=sales.id, style_id=style.id, description=article,
        quantity=quantity, unit_price=0, delivery_date=sales.delivery_date,
    )
    db.add(sales_line)
    db.flush()
    order = ProductionOrder(
        company_id=company_id, sales_order_line_id=sales_line.id, style_id=style.id,
        line_id=None if status == "backlog" else (line.id if line else None),
        order_no=order_no, quantity=quantity, planned_start=start if status != "backlog" else None,
        planned_end=promised,
        status="planned" if status == "backlog" else "in_progress",
        priority=1 if payload.get("urgent") else 3,
        current_stage="backlog" if status == "backlog" else "confeção",
        custom_data={"pmap": True, "client": client_name, "article": article},
    )
    db.add(order)
    db.flush()
    plan = SewingPlan(
        company_id=company_id, code=f"PLAN-{order_no}", production_order_id=order.id, style_id=style.id,
        line_id=None if status == "backlog" else (line.id if line else None),
        source_type="confirmed" if payload.get("source_type") not in {"third_party", "forecast"} else payload.get("source_type"), allocation_type="internal", start_date=start, end_date=end,
        quantity=quantity, sam_minutes=sam, efficiency_pct=100, required_minutes=round(hours * 60, 2),
        probability_pct=100, priority=order.priority, status=status,
    )
    db.add(plan)
    db.flush()
    _write_meta(plan, client=client_name, article=article, sf=0, urgent=payload.get("urgent"), line_key=payload.get("line_key") or (line.code if line else None))
    return plan


def move_block(db: Session, company_id: int, plan_id: int, line_key: str | None, start_date: str | None, extra_hours: bool, action: str = "add", from_date: str | None = None, supplier_id: int | None = None, day_shares: dict | None = None, fabric_quantity: float | None = None, override: bool = False):
    plan = db.get(SewingPlan, plan_id)
    if not plan or plan.company_id != company_id:
        raise ValueError("Ordem não encontrada no mapa")
    items = load_items(db, company_id)
    target = next((row for row in items if row["id"] == plan_id), None)
    if not target:
        raise ValueError("Ordem não encontrada no mapa")
    if action != "remove" and not supplier_id and plan.production_order_id:
        assert_sewing_ready(db, db.get(ProductionOrder, plan.production_order_id), override=override)
    models, _, catalog = _line_maps(db, company_id)
    supplier = db.get(Supplier, supplier_id) if supplier_id else None
    if supplier and supplier.company_id != company_id:
        raise ValueError("Confeçionador inválido")
    line = _line_for_key(models, catalog, line_key or target.get("line_key") or "")
    work_days = list(target.get("work_days") or [])
    shares = dict(target.get("day_share") or {})
    if supplier:
        _save_schedule(db, plan, line=None, supplier=supplier, work_days=[], extra_hours=extra_hours, catalog=catalog, item={**target, "line_key": None, "day_share": {}})
        db.commit()
        board = production_map(db, company_id, extra_hours)
        board["audit_message"] = f"{target['code']} enviada para {supplier.name}."
        return board
    if action == "shares" and day_shares is not None:
        shares = {str(day)[:10]: max(0.0, float(pct)) for day, pct in day_shares.items() if float(pct or 0) > 0}
        work_days = sorted(shares)
    else:
        day = start_date[:10] if start_date else None
        if action == "remove" and day:
            work_days = [item for item in work_days if item != day]
            shares.pop(day, None)
        elif action == "move" and day:
            if from_date:
                old = from_date[:10]
                kept = shares.pop(old, None)
                work_days = [item for item in work_days if item != old]
                if kept and day not in shares:
                    shares[day] = kept
            if day not in work_days:
                work_days.append(day)
        elif day:
            if day not in work_days:
                work_days.append(day)
                used = sum(float(shares.get(key) or 0) for key in work_days)
                leftover = max(0.0, 100.0 - used)
                hours = _item_hours(target.get("quantity"), target.get("sam_minutes"))
                hours_day = _hours_day(catalog, line.code if line else line_key, extra_hours)
                chunk = min(100.0, (hours_day / hours * 100) if hours else leftover)
                shares[day] = round(min(chunk, leftover) or leftover, 1)
        shares = {key: float(shares.get(key) or 0) for key in work_days}
    _save_schedule(db, plan, line=line, supplier=None, work_days=work_days, extra_hours=extra_hours, catalog=catalog, item={**target, "line_key": line.code if line else line_key, "day_share": shares})
    if plan.production_order_id:
        update_order_stage(db, db.get(ProductionOrder, plan.production_order_id))
    db.commit()
    board = production_map(db, company_id, extra_hours)
    left = max(0, (target.get("days_needed") or 1) - len(work_days))
    board["audit_message"] = f"{target['code']} no plano · {len(work_days)} dia(s) marcados" + (f" · faltam {left} dia(s) de trabalho." if left else ".")
    return board


def unschedule_block(db: Session, company_id: int, plan_id: int, extra_hours: bool):
    plan = db.get(SewingPlan, plan_id)
    if not plan or plan.company_id != company_id:
        raise ValueError("Ordem não encontrada")
    items = load_items(db, company_id)
    target = next((row for row in items if row["id"] == plan_id), {"client": None, "article": None, "line_key": None})
    _, _, catalog = _line_maps(db, company_id)
    _save_schedule(db, plan, line=None, supplier=None, work_days=[], extra_hours=extra_hours, catalog=catalog, item=target)
    db.commit()
    return production_map(db, company_id, extra_hours)


def one_click(db: Session, company_id: int, plan_id: int, extra_hours: bool, override: bool = False):
    items = load_items(db, company_id)
    target = next((row for row in items if row["id"] == plan_id), None)
    if not target:
        raise ValueError("Ordem não encontrada")
    plan = db.get(SewingPlan, plan_id)
    if plan and plan.production_order_id:
        assert_sewing_ready(db, db.get(ProductionOrder, plan.production_order_id), override=override)
    models, _, catalog = _line_maps(db, company_id)
    line_key = catalog[0]["key"] if catalog else "L1"
    line = _line_for_key(models, catalog, line_key)
    needed = max(1, int(target.get("days_needed") or 1) - len(target.get("work_days") or []))
    extra = _next_free_days(items, line_key, needed, plan_id)
    work_days = sorted(set((target.get("work_days") or []) + extra))
    plan = db.get(SewingPlan, plan_id)
    _save_schedule(db, plan, line=line, supplier=None, work_days=work_days, extra_hours=extra_hours, catalog=catalog, item={**target, "line_key": line_key})
    db.commit()
    board = production_map(db, company_id, extra_hours)
    board["audit_message"] = f"{target['code']} preenchida na {catalog[0]['name'] if catalog else 'linha'} com os dias livres."
    return board


def shift_one_day(db: Session, company_id: int, plan_id: int, days: int, extra_hours: bool, override: bool = False):
    plan = db.get(SewingPlan, plan_id)
    if not plan or plan.company_id != company_id:
        raise ValueError("Ordem não encontrada")
    items = load_items(db, company_id)
    target = next((row for row in items if row["id"] == plan_id), None)
    if not target or not target.get("work_days"):
        return production_map(db, company_id, extra_hours)
    if plan.production_order_id and days > 0:
        assert_sewing_ready(db, db.get(ProductionOrder, plan.production_order_id), override=override)
    models, _, catalog = _line_maps(db, company_id)
    line = _line_for_key(models, catalog, target.get("line_key") or "")
    shifted = []
    for day in target["work_days"]:
        current = date.fromisoformat(day)
        if days >= 0:
            shifted.append(add_workdays(current, days).isoformat())
        else:
            cursor = current
            left = -days
            while left:
                cursor -= timedelta(days=1)
                if cursor.weekday() < 5:
                    left -= 1
            shifted.append(cursor.isoformat())
    _save_schedule(db, plan, line=line, supplier=None, work_days=shifted, extra_hours=extra_hours, catalog=catalog, item=target)
    db.commit()
    board = production_map(db, company_id, extra_hours)
    board["audit_message"] = "Dias de trabalho deslocados."
    return board


def add_backlog(db: Session, company_id: int, payload: dict, extra_hours: bool):
    _create_order_plan(db, company_id, payload, "backlog", extra_hours)
    db.commit()
    return production_map(db, company_id, extra_hours)


def convert_accept(db: Session, company_id: int, payload: dict, extra_hours: bool):
    items = load_items(db, company_id)
    _, _, catalog = _line_maps(db, company_id)
    placed = _place(items, {
        "article": payload.get("article") or "",
        "quantity": payload.get("quantity"),
        "sam_minutes": payload.get("sam_minutes"),
        "line_key": payload.get("line_key"),
        "client": payload.get("client") or "Cliente",
    }, extra_hours, catalog)
    plan = _create_order_plan(db, company_id, {**payload, **placed, "start_date": placed["start_date"].isoformat()}, "planned", extra_hours)
    remaining = load_items(db, company_id)
    target = next(row for row in remaining if row["id"] == plan.id)
    others = [row for row in remaining if row["id"] != plan.id]
    result, audit = insert_and_push(others, target, monday_of(date.today()), extra_hours)
    persist_items(db, company_id, result, extra_hours)
    db.commit()
    board = production_map(db, company_id, extra_hours)
    board["audit"] = audit
    board["audit_message"] = audit_message(audit, f"{target['code']} convertida em ordem de fabrico.")
    return board


def urgent_insert(db: Session, company_id: int, payload: dict, extra_hours: bool):
    payload = {**payload, "urgent": True}
    plan = _create_order_plan(db, company_id, payload, "planned", extra_hours)
    items = load_items(db, company_id)
    target = next(row for row in items if row["id"] == plan.id)
    others = [row for row in items if row["id"] != plan.id]
    result, audit = insert_and_push(others, {**target, "start_date": date.fromisoformat(payload["start_date"]), "urgent": True}, monday_of(date.today()), extra_hours)
    persist_items(db, company_id, result, extra_hours)
    db.commit()
    board = production_map(db, company_id, extra_hours)
    board["audit"] = audit
    board["impact"] = audit
    board["audit_message"] = audit_message(audit, f"Encomenda urgente {target['code']} encaixada. Relatório de impacto:")
    return board


def toggle_extra(db: Session, company_id: int, extra_hours: bool):
    items = [row for row in load_items(db, company_id) if row.get("start_date")]
    result = apply_extra_hours(items, extra_hours, monday_of(date.today()))
    persist_items(db, company_id, result, extra_hours)
    db.commit()
    return production_map(db, company_id, extra_hours)


def consultant(db: Session, company_id: int, extra_hours: bool):
    items = load_items(db, company_id)
    report = heijunka_consult(items, extra_hours, date.today())
    board = production_map(db, company_id, extra_hours)
    board["consultant"] = report
    return board


def apply_suggestion(db: Session, company_id: int, code: str, to_line: str, extra_hours: bool):
    items = load_items(db, company_id)
    target = next((row for row in items if row["code"] == code), None)
    if not target or not to_line:
        raise ValueError("Sugestão sem movimento aplicável")
    remaining = [row for row in items if row["id"] != target["id"]]
    moved = {**target, "line_key": _canon_line_key(to_line, _line_maps(db, company_id)[2])}
    if not moved.get("start_date"):
        moved = first_fit(remaining, moved, extra_hours, date.today())
        moved["status"] = "planned"
    result, audit = insert_and_push(remaining, moved, monday_of(date.today()), extra_hours)
    persist_items(db, company_id, result, extra_hours)
    db.commit()
    board = production_map(db, company_id, extra_hours)
    board["audit"] = audit
    board["audit_message"] = audit_message(audit, f"{code} movida para Linha {to_line}.")
    return board


def simulate(db: Session, company_id: int, payload: dict, extra_hours: bool):
    items = load_items(db, company_id)
    style = db.get(Style, payload["style_id"]) if payload.get("style_id") else None
    sam = float(payload.get("sam_minutes") or 0)
    article = payload.get("article") or (style.description if style else "")
    if style and not sam:
        from ..models import ProductOperation
        sam = sum(row.smv or 0 for row in db.query(ProductOperation).filter_by(style_id=style.id).all())
    promised = date.fromisoformat(payload["promised_date"]) if payload.get("promised_date") else None
    return simulate_accept(items, float(payload.get("quantity") or 0), sam, promised, extra_hours, date.today(), article)


def apply_faccao(db: Session, company_id: int, extra_hours: bool = False) -> dict:
    board = production_map(db, company_id, extra_hours)
    scenario = next((row for row in board.get("scenarios") or [] if row.get("id") == 3), None)
    hours = float((scenario or {}).get("external_hours") or 0)
    week_no = (scenario or {}).get("week")
    if hours <= 0:
        raise ValueError("Não há sobrecarga suficiente para enviar a facção.")
    service = db.query(SubcontractService).filter(
        SubcontractService.company_id == company_id,
        SubcontractService.active.is_(True),
        SubcontractService.category.in_(["sewing", "finishing"]),
    ).first()
    if not service:
        supplier = db.query(Supplier).filter_by(company_id=company_id, supplier_type="sewing", active=True).first()
        if not supplier:
            raise ValueError("Registe um fornecedor de confeção externa antes de aplicar a facção.")
        service = SubcontractService(
            company_id=company_id, supplier_id=supplier.id, code="CONF-MAP",
            name="Confeção externa (mapa)", category="sewing", unit="h", unit_cost=6.5,
            lead_time_days=7, active=True,
        )
        db.add(service)
        db.flush()
    seq = db.query(SubcontractJob).filter_by(company_id=company_id).count() + 1
    job = SubcontractJob(
        company_id=company_id, subcontract_service_id=service.id, supplier_id=service.supplier_id,
        reference=f"FAC-{date.today().year}-{seq:04d}", quantity=round(hours, 1), unit="h",
        unit_cost=service.unit_cost or 0, planned_cost=round(hours * (service.unit_cost or 0), 2),
        sent_date=date.today(), status="planned",
        notes=f"Gerado pelo mapa de confeção · semana {week_no} · {hours:.1f} h libertadas da carga interna.",
    )
    db.add(job)
    db.commit()
    board = production_map(db, company_id, extra_hours)
    board["audit_message"] = (
        f"Facção {job.reference} criada: {hours:.1f} h na semana {week_no} "
        f"({service.name}). Abra Subcontratos para acompanhar o envio."
    )
    board["faccao_job"] = {"id": job.id, "reference": job.reference, "hours": hours, "week": week_no}
    return board
