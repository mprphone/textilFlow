from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from math import ceil

from ..models import (
    CapacityDay, CapacityEvent, Department, Employee, ExternalCapacity, Machine, Operation,
    ProductOperation, ProductionEvent, ProductionLine, ProductionOrder, SewingPlan,
    Style, Supplier,
)
from .serialization import model_to_dict


ACTIVE_PLAN_STATUS = {"planned", "released", "in_progress", "paused"}
CONFIRMED_SOURCES = {"confirmed", "third_party"}


def _dates(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _working_dates(start: date, end: date) -> list[date]:
    return [day for day in _dates(start, end) if day.weekday() < 5]


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _external_plan_load(db, company_id: int, start: date, end: date) -> dict[tuple[int, date], float]:
    load = defaultdict(float)
    plans = db.query(SewingPlan).filter(
        SewingPlan.company_id == company_id,
        SewingPlan.allocation_type == "external",
        SewingPlan.supplier_id.is_not(None),
        SewingPlan.status.in_(ACTIVE_PLAN_STATUS),
        SewingPlan.end_date >= start,
        SewingPlan.start_date <= end,
    ).all()
    for plan in plans:
        first = _week_start(plan.start_date)
        last = _week_start(plan.end_date)
        weeks = []
        current = first
        while current <= last:
            weeks.append(current)
            current += timedelta(weeks=1)
        quantity, _ = _remaining_plan(db, plan)
        weekly_quantity = quantity / len(weeks) if weeks else 0
        for week in weeks:
            if _week_start(start) <= week <= _week_start(end):
                load[(plan.supplier_id, week)] += weekly_quantity
    return load


def _remaining_plan(db, plan: SewingPlan) -> tuple[float, float]:
    quantity = plan.quantity or 0
    if plan.production_order_id:
        order = db.get(ProductionOrder, plan.production_order_id)
        if order:
            quantity = max(0, (order.quantity or 0) - (order.completed_quantity or 0))
    minutes = quantity * (plan.sam_minutes or 0) / ((plan.efficiency_pct or 85) / 100)
    return quantity, minutes


def _historical_efficiency(db, company_id: int, line_ids: list[int]) -> dict[int, float]:
    since = datetime.combine(date.today() - timedelta(days=60), time.min, tzinfo=timezone.utc)
    rows = db.query(ProductionEvent).filter(
        ProductionEvent.company_id == company_id,
        ProductionEvent.line_id.in_(line_ids),
        ProductionEvent.event_time >= since,
    ).all() if line_ids else []
    actual = defaultdict(float)
    earned = defaultdict(float)
    operations = {row.id: row for row in db.query(Operation).filter_by(company_id=company_id).all()}
    for event in rows:
        actual[event.line_id] += event.duration_minutes or 0
        operation = operations.get(event.operation_id)
        earned[event.line_id] += (operation.standard_time_min if operation else 0) * (event.quantity_good or 0)
    return {
        line_id: round(earned[line_id] / actual[line_id] * 100, 1) if actual[line_id] else 0
        for line_id in line_ids
    }


def capacity_data(db, company_id: int, start: date, end: date) -> dict:
    lines = db.query(ProductionLine).join(Department, Department.id == ProductionLine.department_id).filter(
        ProductionLine.company_id == company_id, ProductionLine.active.is_(True),
        (Department.code.in_(["CONF", "ACAB"])) | Department.name.ilike("%confe%"),
    ).order_by(ProductionLine.name).all()
    if not lines:
        lines = db.query(ProductionLine).filter_by(company_id=company_id, active=True).order_by(ProductionLine.name).all()
    line_ids = [row.id for row in lines]
    history = _historical_efficiency(db, company_id, line_ids)
    capacity_rows = db.query(CapacityDay).filter(
        CapacityDay.company_id == company_id,
        CapacityDay.work_date >= start,
        CapacityDay.work_date <= end,
    ).all()
    capacity_by_day = defaultdict(list)
    for row in capacity_rows:
        capacity_by_day[(row.line_id, row.work_date)].append(row)

    adjustment_rows = db.query(CapacityEvent).filter(
        CapacityEvent.company_id == company_id,
        CapacityEvent.event_date >= start,
        CapacityEvent.event_date <= end,
        CapacityEvent.status != "cancelled",
    ).all()
    adjustments = defaultdict(float)
    event_absences = defaultdict(set)
    for row in adjustment_rows:
        if row.employee_id and row.event_type in {"absence", "vacation"}:
            event_absences[(row.line_id, row.event_date)].add(row.employee_id)
        if row.line_id:
            adjustments[(row.line_id, row.event_date)] += row.minutes_delta or 0
        else:
            for line_id in line_ids:
                adjustments[(line_id, row.event_date)] += row.minutes_delta or 0

    staff = defaultdict(int)
    for employee in db.query(Employee).filter_by(company_id=company_id, active=True).all():
        if employee.line_id:
            staff[employee.line_id] += 1
    machine_total = defaultdict(int)
    machine_available = defaultdict(int)
    for machine in db.query(Machine).filter_by(company_id=company_id, active=True).all():
        if not machine.line_id:
            continue
        machine_total[machine.line_id] += 1
        if machine.status not in {"maintenance", "stopped"}:
            machine_available[machine.line_id] += 1

    actual_rows = db.query(ProductionEvent).filter(
        ProductionEvent.company_id == company_id,
        ProductionEvent.event_time >= datetime.combine(start, time.min, tzinfo=timezone.utc),
        ProductionEvent.event_time < datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc),
    ).all()
    operations = {row.id: row for row in db.query(Operation).filter_by(company_id=company_id).all()}
    actual = defaultdict(lambda: {"minutes": 0.0, "earned": 0.0, "good": 0.0, "rejected": 0.0})
    for event in actual_rows:
        key = (event.line_id, event.event_time.date())
        actual[key]["minutes"] += event.duration_minutes or 0
        actual[key]["good"] += event.quantity_good or 0
        actual[key]["rejected"] += event.quantity_rejected or 0
        operation = operations.get(event.operation_id)
        actual[key]["earned"] += (operation.standard_time_min if operation else 0) * (event.quantity_good or 0)

    plans = db.query(SewingPlan).filter(
        SewingPlan.company_id == company_id,
        SewingPlan.end_date >= start,
        SewingPlan.start_date <= end,
        SewingPlan.status.in_(ACTIVE_PLAN_STATUS),
    ).all()
    plan_load = defaultdict(lambda: {"confirmed": 0.0, "probable": 0.0})
    for plan in plans:
        if plan.allocation_type != "internal" or not plan.line_id:
            continue
        days = _working_dates(max(start, plan.start_date), min(end, plan.end_date))
        if not days:
            continue
        _, remaining_minutes = _remaining_plan(db, plan)
        minutes_day = remaining_minutes / len(_working_dates(plan.start_date, plan.end_date) or days)
        bucket = "confirmed" if plan.source_type in CONFIRMED_SOURCES else "probable"
        weighted = minutes_day if bucket == "confirmed" else minutes_day * (plan.probability_pct or 0) / 100
        for work_date in days:
            plan_load[(plan.line_id, work_date)][bucket] += weighted

    daily = []
    for work_date in _dates(start, end):
        for line in lines:
            rows = capacity_by_day.get((line.id, work_date), [])
            if not rows and work_date.weekday() >= 5:
                continue
            if rows:
                scheduled = sum(row.scheduled_employees or 0 for row in rows)
                absent = sum(row.absent_employees or 0 for row in rows)
                theoretical = sum((row.scheduled_employees or 0) * (row.minutes_per_employee or 0) for row in rows)
                planned = sum(
                    max(0, (row.scheduled_employees or 0) - (row.absent_employees or 0))
                    * max(0, (row.minutes_per_employee or 0) - (row.break_minutes or 0))
                    - (row.setup_minutes or 0) - (row.maintenance_minutes or 0)
                    for row in rows
                )
                configured_efficiency = sum((row.efficiency_pct or 0) * max(1, row.scheduled_employees or 0) for row in rows) / sum(max(1, row.scheduled_employees or 0) for row in rows)
                locked = any(row.locked for row in rows)
            else:
                scheduled = max(staff[line.id], round((line.capacity_minutes_day or 0) / 480), 1)
                absent = 0
                theoretical = scheduled * 480
                planned = scheduled * 450
                configured_efficiency = line.target_efficiency or 85
                locked = False
            planned = max(0, planned + adjustments[(line.id, work_date)])
            displayed_absent = max(absent, len(event_absences[(line.id, work_date)]))
            efficiency = configured_efficiency if locked or not history[line.id] else history[line.id]
            effective = planned * efficiency / 100
            load = plan_load[(line.id, work_date)]
            actual_day = actual[(line.id, work_date)]
            actual_efficiency = actual_day["earned"] / actual_day["minutes"] * 100 if actual_day["minutes"] else 0
            daily.append({
                "date": work_date.isoformat(), "line_id": line.id, "line_code": line.code,
                "line_name": line.name, "scheduled_employees": scheduled,
                "absent_employees": displayed_absent, "present_employees": max(0, scheduled - displayed_absent),
                "machines_available": machine_available[line.id], "machines_total": machine_total[line.id],
                "theoretical_minutes": round(theoretical, 1), "planned_minutes": round(planned, 1),
                "effective_minutes": round(effective, 1), "efficiency_pct": round(efficiency, 1),
                "historical_efficiency_pct": history[line.id], "efficiency_locked": locked,
                "confirmed_minutes": round(load["confirmed"], 1), "probable_minutes": round(load["probable"], 1),
                "load_pct": round(load["confirmed"] / effective * 100, 1) if effective else 0,
                "potential_load_pct": round((load["confirmed"] + load["probable"]) / effective * 100, 1) if effective else 0,
                "free_minutes": round(effective - load["confirmed"] - load["probable"], 1),
                "actual_minutes": round(actual_day["minutes"], 1), "earned_minutes": round(actual_day["earned"], 1),
                "actual_efficiency_pct": round(actual_efficiency, 1), "good_units": actual_day["good"],
                "rejected_units": actual_day["rejected"], "adjustment_minutes": round(adjustments[(line.id, work_date)], 1),
            })
    return {"lines": lines, "plans": plans, "daily": daily}


def confection_overview(db, company_id: int, weeks: int = 8) -> dict:
    start = date.today()
    end = start + timedelta(weeks=weeks, days=-1)
    data = capacity_data(db, company_id, start, end)
    daily = data["daily"]
    today_rows = [row for row in daily if row["date"] == start.isoformat()]
    weekly_groups = defaultdict(list)
    for row in daily:
        weekly_groups[_week_start(date.fromisoformat(row["date"]))].append(row)
    weekly = []
    for week_start in sorted(weekly_groups):
        rows = weekly_groups[week_start]
        effective = sum(row["effective_minutes"] for row in rows)
        confirmed = sum(row["confirmed_minutes"] for row in rows)
        probable = sum(row["probable_minutes"] for row in rows)
        weekly.append({
            "week_start": week_start.isoformat(), "week_end": (week_start + timedelta(days=6)).isoformat(),
            "effective_minutes": round(effective, 1), "confirmed_minutes": round(confirmed, 1),
            "probable_minutes": round(probable, 1), "free_minutes": round(effective - confirmed - probable, 1),
            "load_pct": round(confirmed / effective * 100, 1) if effective else 0,
            "potential_load_pct": round((confirmed + probable) / effective * 100, 1) if effective else 0,
        })
    plans = []
    for row in data["plans"]:
        order = db.get(ProductionOrder, row.production_order_id) if row.production_order_id else None
        style = db.get(Style, row.style_id) if row.style_id else None
        line = db.get(ProductionLine, row.line_id) if row.line_id else None
        supplier = db.get(Supplier, row.supplier_id) if row.supplier_id else None
        remaining_quantity, remaining_minutes = _remaining_plan(db, row)
        plans.append({
            **model_to_dict(row), "order_no": order.order_no if order else None,
            "style_reference": style.reference if style else None,
            "style_description": style.description if style else None,
            "line_name": line.name if line else None, "supplier_name": supplier.name if supplier else None,
            "remaining_quantity": round(remaining_quantity, 1), "remaining_minutes": round(remaining_minutes, 1),
        })
    effective_today = sum(row["effective_minutes"] for row in today_rows)
    confirmed_today = sum(row["confirmed_minutes"] for row in today_rows)
    external_plan_load = _external_plan_load(db, company_id, start, end)
    external_rows = []
    for row in db.query(ExternalCapacity).filter(
        ExternalCapacity.company_id == company_id,
        ExternalCapacity.week_start >= _week_start(start),
        ExternalCapacity.week_start <= _week_start(end),
    ).order_by(ExternalCapacity.week_start).all():
        supplier = db.get(Supplier, row.supplier_id)
        planned = external_plan_load[(row.supplier_id, row.week_start)]
        used = (row.reserved_units or 0) + planned
        external_rows.append({
            **model_to_dict(row), "supplier_name": supplier.name if supplier else "—",
            "planned_units": round(planned, 1), "used_units": round(used, 1),
            "free_units": round((row.capacity_units or 0) - used, 1),
            "load_pct": round(used / row.capacity_units * 100, 1) if row.capacity_units else 0,
        })
    return {
        "date": start.isoformat(),
        "metrics": {
            "scheduled_employees": sum(row["scheduled_employees"] for row in today_rows),
            "present_employees": sum(row["present_employees"] for row in today_rows),
            "machines_available": sum(row["machines_available"] for row in today_rows),
            "machines_total": sum(row["machines_total"] for row in today_rows),
            "theoretical_minutes": round(sum(row["theoretical_minutes"] for row in today_rows), 1),
            "effective_minutes": round(effective_today, 1), "confirmed_minutes": round(confirmed_today, 1),
            "occupancy_pct": round(confirmed_today / effective_today * 100, 1) if effective_today else 0,
            "actual_good_units": sum(row["good_units"] for row in today_rows),
            "actual_rejected_units": sum(row["rejected_units"] for row in today_rows),
        },
        "today_lines": today_rows, "weekly": weekly[:weeks], "plans": plans,
        "external_capacity": external_rows,
        "alerts": [
            {"severity": "danger" if row["potential_load_pct"] > 100 else "warning", "title": f"{row['line_name']} com {row['potential_load_pct']:.1f}% de carga", "date": row["date"]}
            for row in daily if row["potential_load_pct"] > 90
        ][:12],
    }


def _external_completion(db, company_id: int, quantity: float, requested_date: date) -> tuple[float, date | None, float]:
    if quantity <= 0:
        return 0, date.today(), 0
    contractors = db.query(Supplier).filter(
        Supplier.company_id == company_id,
        Supplier.supplier_type == "sewing",
        Supplier.active.is_(True),
    ).all()
    weekly = sum(row.weekly_capacity or 0 for row in contractors)
    unit_cost = 0.0
    if weekly:
        unit_cost = sum((row.weekly_capacity or 0) * (row.piece_cost or 0) for row in contractors) / weekly
        weeks = max(1, ceil(quantity / weekly))
        completion = _week_start(date.today()) + timedelta(weeks=weeks, days=-1)
        lead = max((row.lead_time_days or 0) for row in contractors)
        return quantity, completion + timedelta(days=lead), unit_cost
    rows = db.query(ExternalCapacity).filter(
        ExternalCapacity.company_id == company_id,
        ExternalCapacity.week_start >= _week_start(date.today()),
        ExternalCapacity.status == "available",
    ).order_by(ExternalCapacity.week_start).all()
    plan_load = _external_plan_load(db, company_id, date.today(), rows[-1].week_start + timedelta(days=6) if rows else requested_date)
    remaining = quantity
    allocated = 0.0
    cost = 0.0
    completion = None
    for row in rows:
        free = max(0, (row.capacity_units or 0) - (row.reserved_units or 0) - plan_load[(row.supplier_id, row.week_start)])
        used = min(free, remaining)
        if used <= 0:
            continue
        allocated += used
        remaining -= used
        cost += used * (row.unit_cost or 0)
        completion = row.week_start + timedelta(days=6 + (row.lead_time_days or 0))
        if remaining <= 0:
            break
    return allocated, completion, cost / allocated if allocated else 0


def capacity_check(db, payload) -> dict:
    style = db.get(Style, payload.style_id)
    if not style or style.company_id != payload.company_id:
        raise ValueError("Artigo não encontrado")
    routing = db.query(ProductOperation, Operation).join(
        Operation, Operation.id == ProductOperation.operation_id
    ).filter(ProductOperation.style_id == style.id).all()
    sam = sum((product_operation.smv or operation.standard_time_min or 0) for product_operation, operation in routing)
    if sam <= 0:
        raise ValueError("A ficha do artigo não tem tempos de confeção definidos")
    internal_cost = sum((product_operation.smv or operation.standard_time_min or 0) * (operation.cost_per_minute or 0) for product_operation, operation in routing)
    end = max(payload.requested_date + timedelta(weeks=16), date.today() + timedelta(weeks=26))
    data = capacity_data(db, payload.company_id, date.today(), end)
    free_by_date = defaultdict(float)
    for row in data["daily"]:
        free_by_date[date.fromisoformat(row["date"])] += max(0, row["effective_minutes"] - row["confirmed_minutes"] - row["probable_minutes"])

    def internal_completion(quantity: float) -> date | None:
        required = quantity * sam / 0.85
        for work_date in sorted(free_by_date):
            required -= free_by_date[work_date]
            if required <= 0:
                return work_date
        return None

    scenarios = []
    for name, external_share in [("100% interno", 0), ("70% interno + 30% externo", 0.30), ("50% interno + 50% externo", 0.50)]:
        wanted_external = payload.quantity * external_share
        external_qty, external_date, external_cost = _external_completion(db, payload.company_id, wanted_external, payload.requested_date)
        internal_qty = payload.quantity - external_qty
        internal_date = internal_completion(internal_qty)
        dates = [value for value in [internal_date, external_date if external_qty else None] if value]
        completion = max(dates) if dates else None
        total_cost = internal_qty * internal_cost + external_qty * external_cost
        scenarios.append({
            "name": name, "internal_quantity": round(internal_qty, 1), "external_quantity": round(external_qty, 1),
            "completion_date": completion.isoformat() if completion else None,
            "feasible": bool(completion and completion <= payload.requested_date),
            "unit_cost": round(total_cost / payload.quantity, 4) if payload.quantity else 0,
        })
    recommended = next((index for index, row in enumerate(scenarios) if row["feasible"]), None)
    return {
        "style": {"id": style.id, "reference": style.reference, "description": style.description},
        "quantity": payload.quantity, "requested_date": payload.requested_date.isoformat(),
        "sam_minutes": round(sam, 3), "scenarios": scenarios, "recommended_scenario": recommended,
    }
