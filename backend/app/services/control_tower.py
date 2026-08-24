from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import (
    CapacityDay, CapacityEvent, CorrectiveAction, OperationalAlert, ProductOperation,
    ProductionLine, ProductionMaterialRequirement, ProductionOrder, QualityInspection,
    SalesOrder, SalesOrderLine, SubcontractJob,
)
from .cost_control import order_control
from .serialization import model_to_dict


ACTIVE_ORDER_STATUSES = {"planned", "released", "in_progress", "paused", "partial"}


def _workdays(start: date, count: int = 90):
    cursor = start
    yielded = 0
    while yielded < count:
        if cursor.weekday() < 5:
            yield cursor
            yielded += 1
        cursor += timedelta(days=1)


def _capacity(db: Session, company_id: int, line: ProductionLine, day: date) -> float:
    rows = db.query(CapacityDay).filter_by(company_id=company_id, line_id=line.id, work_date=day).all()
    if rows:
        minutes = sum(
            max(0.0, (row.scheduled_employees - row.absent_employees) * row.minutes_per_employee
                - row.break_minutes - row.setup_minutes - row.maintenance_minutes)
            * row.efficiency_pct / 100 for row in rows
        )
    else:
        minutes = float(line.capacity_minutes_day or 0) * float(line.target_efficiency or 100) / 100
    event_delta = sum(float(row.minutes_delta or 0) for row in db.query(CapacityEvent).filter_by(
        company_id=company_id, line_id=line.id, event_date=day, status="confirmed"
    ).all())
    return round(max(0.0, minutes + event_delta), 2)


def _required_minutes(db: Session, order: ProductionOrder) -> float:
    remaining = max(0.0, float(order.quantity or 0) - float(order.completed_quantity or 0))
    smv = sum(float(row.smv or 0) for row in db.query(ProductOperation).filter_by(
        company_id=order.company_id, style_id=order.style_id
    ).all())
    if smv <= 0:
        smv = float((order.custom_data or {}).get("sam_minutes") or 1)
    return round(remaining * smv, 2)


def finite_plan(db: Session, company_id: int, *, apply: bool = False) -> dict:
    """Sequencia OF por prioridade e prazo contra capacidade diária efetiva."""
    today = date.today()
    lines = db.query(ProductionLine).filter_by(company_id=company_id, active=True).order_by(ProductionLine.code).all()
    orders = db.query(ProductionOrder).filter_by(company_id=company_id).filter(
        ProductionOrder.status.in_(ACTIVE_ORDER_STATUSES)
    ).all()
    orders.sort(key=lambda row: (int(row.priority or 3), row.planned_end or date.max, row.id))
    if not lines:
        return {"generated_at": datetime.now(timezone.utc).isoformat(), "applied": False, "lines": [], "orders": [], "warning": "Não existem linhas de produção ativas."}

    days = list(_workdays(today, 90))
    remaining_capacity = {(line.id, day): _capacity(db, company_id, line, day) for line in lines for day in days}
    load = defaultdict(float)
    result = []
    for sequence, order in enumerate(orders, start=1):
        required = _required_minutes(db, order)
        candidates = [line for line in lines if line.id == order.line_id] or lines
        line = min(candidates, key=lambda item: load[item.id])
        outstanding = required
        used_days = []
        for day in days:
            available = remaining_capacity[(line.id, day)]
            if available <= 0 or outstanding <= 0:
                continue
            take = min(available, outstanding)
            remaining_capacity[(line.id, day)] -= take
            outstanding -= take
            load[line.id] += take
            used_days.append(day)
        start = used_days[0] if used_days else None
        end = used_days[-1] if used_days else None
        promised = order.planned_end
        late_days = max(0, (end - promised).days) if end and promised else 0
        result.append({
            "sequence": sequence, "production_order_id": order.id, "order_no": order.order_no,
            "line_id": line.id, "line": line.name, "required_minutes": required,
            "planned_start": start.isoformat() if start else None, "planned_end": end.isoformat() if end else None,
            "promised_date": promised.isoformat() if promised else None, "late_days": late_days,
            "unallocated_minutes": round(outstanding, 2),
            "risk": "late" if late_days else "capacity" if outstanding else "on_track",
        })
        if apply and start and end:
            order.line_id = line.id
            order.planned_start = start
            order.planned_end = end
            data = dict(order.custom_data or {})
            data.update({"finite_plan_sequence": sequence, "finite_plan_generated_at": datetime.now(timezone.utc).isoformat()})
            order.custom_data = data
    if apply:
        db.flush()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(), "applied": apply,
        "lines": [{"id": line.id, "code": line.code, "name": line.name, "planned_minutes": round(load[line.id], 2), "capacity_minutes": round(sum(_capacity(db, company_id, line, day) for day in days), 2)} for line in lines],
        "orders": result,
    }


def _upsert_alert(db: Session, company_id: int, spec: dict) -> OperationalAlert:
    values = dict(spec)
    fingerprint = values.pop("fingerprint")
    row = db.query(OperationalAlert).filter_by(company_id=company_id, fingerprint=fingerprint).first()
    reopened = bool(row and row.status != "open")
    if not row:
        row = OperationalAlert(company_id=company_id, fingerprint=fingerprint)
        db.add(row)
    for key, value in values.items():
        setattr(row, key, value)
    row.status = "open"
    row.resolved_at = None
    if reopened:
        row.detected_at = datetime.now(timezone.utc)
        row.seen_at = None
        row.seen_by = None
        metadata = dict(row.metadata_json or {})
        metadata["occurrence"] = int(metadata.get("occurrence") or 1) + 1
        row.metadata_json = metadata
    return row


def refresh_alerts(db: Session, company_id: int, plan: dict | None = None) -> list[OperationalAlert]:
    today = date.today()
    active_fingerprints = set()
    specs = []
    orders = db.query(ProductionOrder).filter_by(company_id=company_id).filter(ProductionOrder.status.in_(ACTIVE_ORDER_STATUSES)).all()
    plan_by_order = {row["production_order_id"]: row for row in (plan or {}).get("orders", [])}
    for order in orders:
        base = {"production_order_id": order.id, "action_route": f"tracking?order={order.id}", "action_label": "Abrir OF"}
        if order.planned_end and order.planned_end < today:
            specs.append({**base, "fingerprint": f"overdue:{order.id}", "code": "overdue", "severity": "critical", "title": f"{order.order_no} está atrasada", "detail": f"Prazo planeado: {order.planned_end.isoformat()}."})
        shortage = sum(float(row.shortage_quantity or 0) for row in db.query(ProductionMaterialRequirement).filter_by(production_order_id=order.id).all())
        if shortage > 0:
            specs.append({**base, "fingerprint": f"material-shortage:{order.id}", "code": "material_shortage", "severity": "critical", "title": f"Falta material em {order.order_no}", "detail": f"Saldo agregado em falta: {shortage:g}."})
        late = plan_by_order.get(order.id)
        if late and (late["late_days"] or late["unallocated_minutes"]):
            specs.append({**base, "fingerprint": f"schedule-risk:{order.id}", "code": "schedule_risk", "severity": "warning", "title": f"Risco de prazo em {order.order_no}", "detail": f"Plano finito: {late['late_days']} dias de atraso; {late['unallocated_minutes']:g} min sem capacidade."})
        final = db.query(QualityInspection).filter_by(production_order_id=order.id).filter(QualityInspection.inspection_type.in_(["final", "revista"])).all()
        if float(order.completed_quantity or 0) > 0 and not any(row.result in {"passed", "conditional"} for row in final):
            specs.append({**base, "fingerprint": f"quality-pending:{order.id}", "code": "quality_pending", "severity": "warning", "title": f"{order.order_no} aguarda decisão de qualidade", "detail": "Existe produção concluída sem libertação final/revista.", "action_route": "quality", "action_label": "Inspecionar"})
        from .shipping import approved_quantity
        approved = approved_quantity(db, order)
        from .execution import movement_holdings
        packed = max(
            float(movement_holdings(db, order)["packed"]),
            float((order.custom_data or {}).get("packed_quantity") or 0),
        )
        if approved > packed + 0.001:
            specs.append({**base, "fingerprint": f"ready-pack:{order.id}", "code": "ready_to_pack", "severity": "info", "title": f"{order.order_no} tem peças prontas a embalar", "detail": f"{approved - packed:g} unidades aprovadas aguardam embalagem.", "action_route": "embalagem", "action_label": "Abrir embalagem"})
    for job in db.query(SubcontractJob).filter_by(company_id=company_id).filter(SubcontractJob.status.in_(["planned", "sent", "partial", "problem"])).all():
        if job.status == "problem" or (job.expected_date and job.expected_date < today and job.status != "received"):
            specs.append({"production_order_id": job.production_order_id, "fingerprint": f"subcontract-risk:{job.id}", "code": "subcontract_risk", "severity": "critical" if job.status == "problem" else "warning", "title": f"Subcontrato {job.reference} requer atenção", "detail": f"Estado: {job.status}; data prevista: {job.expected_date or 'sem data'}.", "action_route": "subcontracts", "action_label": "Abrir subcontratos"})
    for capa in db.query(CorrectiveAction).filter_by(company_id=company_id).filter(CorrectiveAction.status.notin_(["verified", "closed"])).all():
        due = capa.due_date.date() if capa.due_date else None
        if due and due < today:
            specs.append({"fingerprint": f"capa-overdue:{capa.id}", "code": "capa_overdue", "severity": "critical", "title": f"Ação corretiva #{capa.id} em atraso", "detail": f"Prazo: {due.isoformat()}.", "action_route": "quality", "action_label": "Abrir qualidade"})
    from .shipping import dispatch_status
    sales_orders = db.query(SalesOrder).filter_by(company_id=company_id).filter(SalesOrder.status.notin_(["cancelled", "shipped"])).all()
    for sales_order in sales_orders:
        status = dispatch_status(db, sales_order)
        if status.get("ready"):
            specs.append({"fingerprint": f"ready-ship:{sales_order.id}", "code": "ready_to_ship", "severity": "info", "title": f"Encomenda {sales_order.order_no} pronta para expedição parcial", "detail": status.get("reason"), "action_route": "shipping", "action_label": "Preparar expedição"})
    for spec in specs:
        active_fingerprints.add(spec["fingerprint"])
        _upsert_alert(db, company_id, spec)
    for row in db.query(OperationalAlert).filter_by(company_id=company_id, status="open").all():
        if row.fingerprint not in active_fingerprints:
            row.status = "resolved"
            row.resolved_at = datetime.now(timezone.utc)
    db.flush()
    return db.query(OperationalAlert).filter_by(company_id=company_id, status="open").order_by(OperationalAlert.detected_at.desc()).all()


def _commercial_value(db: Session, order: ProductionOrder) -> float:
    line = db.get(SalesOrderLine, order.sales_order_line_id) if order.sales_order_line_id else None
    return round(float(line.quantity or 0) * float(line.unit_price or 0), 2) if line else 0.0


def control_tower(db: Session, company_id: int) -> dict:
    plan = finite_plan(db, company_id)
    alerts = refresh_alerts(db, company_id, plan)
    orders = db.query(ProductionOrder).filter_by(company_id=company_id).filter(ProductionOrder.status.in_(ACTIVE_ORDER_STATUSES)).order_by(ProductionOrder.priority, ProductionOrder.planned_end).all()
    order_rows = []
    forecast_cost = revenue = 0.0
    for order in orders:
        control = order_control(db, order)
        metrics = control.get("metrics") or {}
        value = _commercial_value(db, order)
        forecast = float(metrics.get("forecast_total") or metrics.get("actual_total") or 0)
        forecast_cost += forecast
        revenue += value
        order_rows.append({**model_to_dict(order), "revenue": value, "forecast_cost": round(forecast, 2), "forecast_margin": round(value - forecast, 2), "cost_status": metrics.get("status", "no_baseline"), "schedule": next((row for row in plan["orders"] if row["production_order_id"] == order.id), None)})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kpis": {"active_orders": len(orders), "critical_alerts": sum(row.severity == "critical" for row in alerts), "open_alerts": len(alerts), "forecast_revenue": round(revenue, 2), "forecast_cost": round(forecast_cost, 2), "forecast_margin": round(revenue - forecast_cost, 2)},
        "alerts": [model_to_dict(row) for row in alerts], "plan": plan, "orders": order_rows,
    }
