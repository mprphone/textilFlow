from __future__ import annotations

import json
from datetime import date, timedelta
from math import ceil

from sqlalchemy.orm import Session

from ..models import (
    Customer, Department, Machine, ProcessJob, ProductionLine, ProductionOrder,
    SalesOrder, SalesOrderLine, Style, Supplier,
)
from .confection_schedule import build_board, next_workday, order_hours
from .fabric_flow import fabric_status_map, gate_and_maybe_consume


MAP_NOTE = "cmap"
LINE_COLORS = ("green", "blue", "teal", "orange")
PROCESS = "cutting"


def _dept_is_cut(department) -> bool:
    if not department:
        return False
    code = (department.code or "").upper()
    name = (department.name or "").lower()
    return code in {"COR", "CORTE", "CUT"} or "corte" in name or "cut" in name


def company_cutting_catalog(db: Session, company_id: int) -> list[dict]:
    departments = {row.id: row for row in db.query(Department).filter_by(company_id=company_id).all()}
    lines = [
        row for row in db.query(ProductionLine).filter_by(company_id=company_id, active=True).order_by(ProductionLine.id).all()
        if _dept_is_cut(departments.get(row.department_id))
    ]
    dept_ids = {row.id for row in departments.values() if _dept_is_cut(row)}
    machines = [
        row for row in db.query(Machine).filter_by(company_id=company_id).order_by(Machine.id).all()
        if row.department_id in dept_ids
    ]
    catalog = []
    if machines:
        share = max(1, len(machines))
        room_minutes = (lines[0].capacity_minutes_day or 480) if lines else 480
        hours_day = max(8.0, room_minutes / 60 / share)
        for index, machine in enumerate(machines):
            catalog.append({
                "key": machine.code,
                "id": machine.line_id or (lines[0].id if lines else None),
                "machine_id": machine.id,
                "code": machine.code,
                "name": machine.name,
                "family": "",
                "posts": "",
                "pcs_hour": machine.target_units_hour or 0,
                "color": LINE_COLORS[index % len(LINE_COLORS)],
                "hours_day": hours_day,
            })
        return catalog
    for index, row in enumerate(lines):
        catalog.append({
            "key": row.code,
            "id": row.id,
            "machine_id": None,
            "code": row.code,
            "name": row.name,
            "family": "",
            "posts": "",
            "pcs_hour": row.target_pcs_hour or 0,
            "color": LINE_COLORS[index % len(LINE_COLORS)],
            "hours_day": max(8.0, (row.capacity_minutes_day or 480) / 60),
        })
    return catalog


def _line_maps(db: Session, company_id: int):
    catalog = company_cutting_catalog(db, company_id)
    lines = db.query(ProductionLine).filter_by(company_id=company_id).all()
    models = {row.code: row for row in lines}
    by_id = {row.id: row.code for row in lines}
    return models, by_id, catalog


def _meta(job: ProcessJob) -> dict:
    try:
        data = json.loads(job.notes or "")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_meta(job: ProcessJob, **fields):
    meta = _meta(job)
    meta[MAP_NOTE] = True
    meta.update({key: value for key, value in fields.items() if value is not None})
    job.notes = json.dumps(meta, ensure_ascii=False)


def _as_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _hours_day(catalog: list[dict], line_key: str | None, extra_hours: bool) -> float:
    line = next((row for row in catalog if row["key"] == line_key), None)
    base = (line or {}).get("hours_day") or 8.0
    return base * 1.25 if extra_hours else base


def _item_hours(quantity, sam) -> float:
    return round(order_hours(quantity or 0, sam or 0), 1)


def _days_needed(hours: float, hours_day: float) -> int:
    if hours_day <= 0:
        return 1
    return max(1, ceil(hours / hours_day)) if hours else 1


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


def _catalog_item(catalog: list[dict], line_key: str | None) -> dict | None:
    if line_key:
        found = next((row for row in catalog if row["key"] == line_key), None)
        if found:
            return found
    return catalog[0] if catalog else None


def _resolve_line_key(job: ProcessJob, meta: dict, catalog: list[dict]) -> str:
    if meta.get("line_key") and any(row["key"] == meta["line_key"] for row in catalog):
        return meta["line_key"]
    if job.machine_id:
        found = next((row for row in catalog if row.get("machine_id") == job.machine_id), None)
        if found:
            return found["key"]
    if job.line_id:
        found = next((row for row in catalog if row.get("id") == job.line_id), None)
        if found:
            return found["key"]
    return catalog[0]["key"] if catalog else ""


def _work_days_from(job: ProcessJob, meta: dict) -> list[str]:
    stored = meta.get("work_days")
    if isinstance(stored, list) and stored:
        return sorted({str(day)[:10] for day in stored if day})
    if job.status == "backlog" or not job.planned_date:
        return []
    return [job.planned_date.isoformat()]


def _promised(db: Session, order: ProductionOrder | None, meta: dict):
    promised = _as_date(meta.get("promised_date"))
    if order and order.sales_order_line_id:
        line = db.get(SalesOrderLine, order.sales_order_line_id)
        sales = db.get(SalesOrder, line.sales_order_id) if line else None
        if sales and sales.delivery_date:
            promised = promised or sales.delivery_date
    if order and order.planned_end:
        promised = promised or order.planned_end
    return promised


def _customer_name(db: Session, order: ProductionOrder | None, meta: dict) -> str:
    if meta.get("client"):
        return meta["client"]
    if order and order.sales_order_line_id:
        line = db.get(SalesOrderLine, order.sales_order_line_id)
        sales = db.get(SalesOrder, line.sales_order_id) if line else None
        customer = db.get(Customer, sales.customer_id) if sales else None
        if customer:
            return customer.name
    return "Cliente"


def load_items(db: Session, company_id: int) -> list[dict]:
    _, _, catalog = _line_maps(db, company_id)
    jobs = db.query(ProcessJob).filter(
        ProcessJob.company_id == company_id,
        ProcessJob.process_kind == PROCESS,
        ProcessJob.status.notin_(["completed", "cancelled"]),
    ).all()
    items = []
    for job in jobs:
        meta = _meta(job)
        order = db.get(ProductionOrder, job.production_order_id) if job.production_order_id else None
        style = db.get(Style, order.style_id) if order and order.style_id else None
        line_key = _resolve_line_key(job, meta, catalog)
        sam = float(meta.get("sam_minutes") or 2.5)
        hours = _item_hours(job.quantity, sam)
        hours_day = _hours_day(catalog, line_key, False)
        work_days = _work_days_from(job, meta)
        needed = _days_needed(hours, hours_day)
        allocation = meta.get("allocation_type") or "internal"
        supplier = db.get(Supplier, meta.get("supplier_id")) if meta.get("supplier_id") else None
        promised = _promised(db, order, meta)
        items.append({
            "id": job.id,
            "code": (order.order_no if order else job.reference),
            "order_id": order.id if order else None,
            "client": _customer_name(db, order, meta),
            "article": meta.get("article") or (style.description if style else job.reference),
            "quantity": job.quantity,
            "sam_minutes": sam,
            "hours": hours,
            "hours_day": hours_day,
            "days_needed": needed,
            "work_days": work_days,
            "day_share": _day_shares(meta, work_days, hours, hours_day),
            "days_planned": len(work_days),
            "days_left": max(0, needed - len(work_days)),
            "source_type": "confirmed",
            "line_key": None if allocation == "external" else line_key,
            "status": "backlog" if job.status == "backlog" or (allocation != "external" and not work_days) else job.status,
            "urgent": bool(meta.get("urgent")),
            "start_date": None if not work_days or allocation == "external" else work_days[0],
            "end_date": work_days[-1] if work_days else None,
            "start_fraction": 0,
            "promised_date": promised.isoformat() if promised else None,
            "due_in_days": (promised - date.today()).days if promised else None,
            "allocation_type": allocation,
            "supplier_id": supplier.id if supplier else None,
            "supplier_name": supplier.name if supplier else None,
            "notes": job.notes,
        })
    statuses = fabric_status_map(db, company_id, [row["order_id"] for row in items])
    for row in items:
        status = statuses.get(row["order_id"]) or {"ready": True, "label": "Sem malha na ficha", "needed": 0, "unit": "kg", "missing": 0, "covered": 0, "issued": 0}
        row["fabric_ready"] = status["ready"]
        row["fabric_label"] = status["label"]
        row["fabric_needed"] = status.get("needed") or 0
        row["fabric_unit"] = status.get("unit") or "kg"
        row["fabric_missing"] = status.get("missing") or 0
        row["fabric_covered"] = status.get("covered") or 0
        row["fabric_issued"] = status.get("issued") or 0
    return items


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


def _save_schedule(db: Session, job: ProcessJob, *, catalog_item, supplier, work_days: list[str], extra_hours: bool, catalog, item: dict):
    hours = _item_hours(job.quantity, item.get("sam_minutes") or 2.5)
    hours_day = _hours_day(catalog, item.get("line_key"), extra_hours)
    work_days = sorted({str(day)[:10] for day in work_days if day})
    if supplier:
        job.status = "planned"
        job.line_id = None
        job.machine_id = None
        job.planned_date = date.today()
        work_days = []
        allocation = "external"
        supplier_id = supplier.id
        line_key = None
    elif work_days:
        job.status = "planned"
        job.line_id = catalog_item.get("id") if catalog_item else None
        job.machine_id = catalog_item.get("machine_id") if catalog_item else None
        job.planned_date = date.fromisoformat(work_days[0])
        allocation = "internal"
        supplier_id = None
        line_key = catalog_item.get("key") if catalog_item else item.get("line_key")
    else:
        job.status = "backlog"
        job.line_id = None
        job.machine_id = None
        job.planned_date = None
        allocation = "internal"
        supplier_id = None
        line_key = None
    _write_meta(
        job,
        client=item.get("client"),
        article=item.get("article"),
        sam_minutes=item.get("sam_minutes"),
        promised_date=item.get("promised_date"),
        line_key=line_key,
        work_days=work_days,
        day_share=_day_shares({"day_share": item.get("day_share")}, work_days, hours, hours_day) if work_days else {},
        days_needed=_days_needed(hours, hours_day),
        allocation_type=allocation,
        supplier_id=supplier_id,
        urgent=item.get("urgent"),
    )
    if job.production_order_id:
        order = db.get(ProductionOrder, job.production_order_id)
        if order and job.status != "backlog":
            order.planned_start = job.planned_date or order.planned_start
            if work_days:
                order.current_stage = "corte externo" if allocation == "external" else "corte"


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
        for row in db.query(Supplier).filter(
            Supplier.company_id == company_id, Supplier.active.is_(True),
            Supplier.supplier_type.in_(["cutting", "cut", "corte"]),
        ).order_by(Supplier.name).all()
    ]
    if not board["contractors"]:
        board["contractors"] = [
            {
                "id": row.id, "name": row.name, "weekly_capacity": row.weekly_capacity or 0,
                "piece_cost": row.piece_cost or 0, "lead_time_days": row.lead_time_days or 0,
            }
            for row in db.query(Supplier).filter_by(company_id=company_id, active=True).order_by(Supplier.name).all()
            if "cort" in f"{row.supplier_type or ''} {row.name or ''}".lower()
        ]
    board["area"] = "cutting"
    return board


def _next_ref(db: Session, company_id: int) -> str:
    count = db.query(ProcessJob).filter_by(company_id=company_id, process_kind=PROCESS).count() + 1
    return f"COR-{date.today().year}-{count:04d}"


def ensure_cutting_job_for_order(db: Session, order: ProductionOrder, *, client: str | None = None, article: str | None = None, sam_minutes: float = 2.5) -> ProcessJob:
    existing = db.query(ProcessJob).filter_by(
        company_id=order.company_id, process_kind=PROCESS, production_order_id=order.id,
    ).first()
    if existing:
        return existing
    job = ProcessJob(
        company_id=order.company_id,
        process_kind=PROCESS,
        production_order_id=order.id,
        reference=order.order_no,
        quantity=order.quantity or 0,
        unit="un",
        status="backlog",
    )
    db.add(job)
    db.flush()
    _write_meta(
        job, client=client or "Cliente", article=article or order.order_no,
        sam_minutes=sam_minutes, promised_date=order.planned_end.isoformat() if order.planned_end else None,
        allocation_type="internal", work_days=[], day_share={},
    )
    return job


def add_backlog(db: Session, company_id: int, payload: dict, extra_hours: bool):
    article = payload.get("article") or "Artigo"
    client = payload.get("client") or "Cliente"
    quantity = float(payload.get("quantity") or 0)
    sam = float(payload.get("sam_minutes") or 2.5)
    promised = _as_date(payload.get("promised_date"))
    job = ProcessJob(
        company_id=company_id,
        process_kind=PROCESS,
        reference=payload.get("code") or _next_ref(db, company_id),
        quantity=quantity,
        unit="un",
        status="backlog",
        production_order_id=payload.get("production_order_id") or None,
    )
    db.add(job)
    db.flush()
    _write_meta(job, client=client, article=article, sam_minutes=sam, promised_date=promised.isoformat() if promised else None, allocation_type="internal", work_days=[], day_share={})
    db.commit()
    return production_map(db, company_id, extra_hours)


def move_block(db: Session, company_id: int, plan_id: int, line_key: str | None, start_date: str | None, extra_hours: bool, action: str = "add", from_date: str | None = None, supplier_id: int | None = None, day_shares: dict | None = None, fabric_quantity: float | None = None, user_id: int | None = None):
    job = db.get(ProcessJob, plan_id)
    if not job or job.company_id != company_id or job.process_kind != PROCESS:
        raise ValueError("Ordem não encontrada no mapa de corte")
    items = load_items(db, company_id)
    target = next((row for row in items if row["id"] == plan_id), None)
    if not target:
        raise ValueError("Ordem não encontrada no mapa de corte")
    issued = None
    if action != "remove" and job.production_order_id:
        order = db.get(ProductionOrder, job.production_order_id)
        first_day = not (target.get("work_days") or [])
        issued = gate_and_maybe_consume(
            db, company_id=company_id, user_id=user_id, order=order, stage="cutting",
            first_day=first_day, fabric_quantity=fabric_quantity,
        )
    _, _, catalog = _line_maps(db, company_id)
    supplier = db.get(Supplier, supplier_id) if supplier_id else None
    if supplier and supplier.company_id != company_id:
        raise ValueError("Fornecedor inválido")
    resource = _catalog_item(catalog, line_key or target.get("line_key") or "")
    work_days = list(target.get("work_days") or [])
    shares = dict(target.get("day_share") or {})
    if supplier:
        _save_schedule(db, job, catalog_item=None, supplier=supplier, work_days=[], extra_hours=extra_hours, catalog=catalog, item={**target, "line_key": None, "day_share": {}})
        db.commit()
        board = production_map(db, company_id, extra_hours)
        board["audit_message"] = f"{target['code']} enviada para corte fora ({supplier.name})." + (
            f" Saída {issued['doc_no']} · {issued['taken']} {issued['unit']}." if isinstance(issued, dict) and issued.get("doc_no") else ""
        )
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
                hours_day = _hours_day(catalog, resource["key"] if resource else line_key, extra_hours)
                chunk = min(100.0, (hours_day / hours * 100) if hours else leftover)
                shares[day] = round(min(chunk, leftover) or leftover, 1)
        shares = {key: float(shares.get(key) or 0) for key in work_days}
    _save_schedule(
        db, job, catalog_item=resource, supplier=None, work_days=work_days, extra_hours=extra_hours,
        catalog=catalog, item={**target, "line_key": resource["key"] if resource else line_key, "day_share": shares},
    )
    db.commit()
    board = production_map(db, company_id, extra_hours)
    left = max(0, (target.get("days_needed") or 1) - len(work_days))
    message = f"{target['code']} no plano de corte · {len(work_days)} dia(s)" + (f" · faltam {left} dia(s)" if left else "")
    if isinstance(issued, dict) and issued.get("doc_no"):
        message += f" · documento {issued['doc_no']} · {issued['taken']} {issued['unit']} de malha"
    elif isinstance(issued, dict) and issued.get("waiting_stock"):
        message += f" · planeada sem stock ({issued.get('label')})"
    board["audit_message"] = message + "."
    return board


def unschedule_block(db: Session, company_id: int, plan_id: int, extra_hours: bool):
    job = db.get(ProcessJob, plan_id)
    if not job or job.company_id != company_id or job.process_kind != PROCESS:
        raise ValueError("Ordem não encontrada")
    items = load_items(db, company_id)
    target = next((row for row in items if row["id"] == plan_id), {"client": None, "article": None, "line_key": None})
    _, _, catalog = _line_maps(db, company_id)
    _save_schedule(db, job, catalog_item=None, supplier=None, work_days=[], extra_hours=extra_hours, catalog=catalog, item=target)
    db.commit()
    return production_map(db, company_id, extra_hours)


def one_click(db: Session, company_id: int, plan_id: int, extra_hours: bool, fabric_quantity: float | None = None, user_id: int | None = None):
    items = load_items(db, company_id)
    target = next((row for row in items if row["id"] == plan_id), None)
    if not target:
        raise ValueError("Ordem não encontrada")
    job = db.get(ProcessJob, plan_id)
    issued = None
    if job and job.production_order_id:
        first_day = not (target.get("work_days") or [])
        issued = gate_and_maybe_consume(
            db, company_id=company_id, user_id=user_id, order=db.get(ProductionOrder, job.production_order_id),
            stage="cutting", first_day=first_day, fabric_quantity=fabric_quantity,
        )
    _, _, catalog = _line_maps(db, company_id)
    if not catalog:
        raise ValueError("Crie mesas ou máquinas de corte para planear")
    line_key = catalog[0]["key"]
    resource = catalog[0]
    needed = max(1, int(target.get("days_needed") or 1) - len(target.get("work_days") or []))
    extra = _next_free_days(items, line_key, needed, plan_id)
    work_days = sorted(set((target.get("work_days") or []) + extra))
    job = db.get(ProcessJob, plan_id)
    _save_schedule(db, job, catalog_item=resource, supplier=None, work_days=work_days, extra_hours=extra_hours, catalog=catalog, item={**target, "line_key": line_key})
    db.commit()
    board = production_map(db, company_id, extra_hours)
    board["audit_message"] = f"{target['code']} preenchida na {resource['name']} com os dias livres." + (
        f" Saída {issued['doc_no']} · {issued['taken']} {issued['unit']}." if isinstance(issued, dict) and issued.get("doc_no") else ""
    )
    return board
