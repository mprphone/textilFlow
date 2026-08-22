from datetime import date, datetime, timedelta

from sqlalchemy import func

from ..models import (
    Certification, Company, CuttingJob, DowntimeEvent, Employee, Machine, Operation, ProductOperation,
    ProductionEvent, ProductionLine, ProductionOrder, QualityInspection, Sample, StockLot, Style,
)

DOWNTIME_REASON_LABEL = {
    "breakdown": "Avaria", "setup": "Preparação/mudança", "material": "Falta de material",
    "quality": "Paragem de qualidade", "maintenance": "Manutenção planeada", "no_operator": "Sem operador",
    "other": "Outro",
}


def _earned_minutes_resolver(db, company_id: int):
    """Resolve minutos-padrao por evento usando o SMV do artigo (ProductOperation),
    com fallback para o tempo generico da operacao - a mesma prioridade ja usada em
    costing.py e confection_capacity.py::capacity_check, agora tambem aqui. Pre-carrega
    tudo de uma vez para nao repetir uma query por evento."""
    operations = {row.id: row for row in db.query(Operation).filter_by(company_id=company_id).all()}
    orders = {row.id: row for row in db.query(ProductionOrder).filter_by(company_id=company_id).all()}
    smv_by_style_operation = {}
    for row in db.query(ProductOperation).filter_by(company_id=company_id).all():
        if row.smv:
            smv_by_style_operation[(row.style_id, row.operation_id)] = row.smv

    def earned_minutes(event) -> float:
        operation = operations.get(event.operation_id)
        order = orders.get(event.production_order_id)
        style_smv = smv_by_style_operation.get((order.style_id, event.operation_id)) if order else None
        minutes = style_smv or (operation.standard_time_min if operation else 0) or 0
        return minutes * (event.quantity_good or 0)

    return earned_minutes


def _in_period(event, start: date | None, end: date | None) -> bool:
    if not start and not end:
        return True
    when = event.event_time
    if when is None:
        return False
    day = when.date() if isinstance(when, datetime) else when
    if start and day < start:
        return False
    if end and day > end:
        return False
    return True


def dashboard_metrics(db, company_id: int, start: date | None = None, end: date | None = None) -> dict:
    orders = db.query(ProductionOrder).filter_by(company_id=company_id).all()
    events = [row for row in db.query(ProductionEvent).filter_by(company_id=company_id).all() if _in_period(row, start, end)]
    quality = db.query(QualityInspection).filter_by(company_id=company_id).all()
    total_planned = sum(row.quantity for row in orders)
    total_completed = sum(row.completed_quantity for row in orders)
    good = sum(row.quantity_good for row in events)
    rejected = sum(row.quantity_rejected for row in events)
    minutes = sum(row.duration_minutes for row in events)
    labor_cost = sum(row.labor_cost for row in events)
    machine_cost = sum(row.machine_cost for row in events)
    inspection_defects = sum(row.defect_quantity for row in quality)
    active = [row for row in orders if row.status not in {"completed", "cancelled"}]
    at_risk = [row for row in active if row.planned_end and row.planned_end <= date.today() + timedelta(days=3)]
    alerts = build_alerts(db, company_id, orders)
    return {
        "orders_active": len(active),
        "orders_at_risk": len(at_risk),
        "planned_quantity": total_planned,
        "completed_quantity": total_completed,
        "completion_pct": round(total_completed / total_planned * 100, 1) if total_planned else 0,
        "output_good": good,
        "output_rejected": rejected,
        "quality_rate": round(good / (good + rejected + inspection_defects) * 100, 1) if good + rejected + inspection_defects else 100,
        "productive_hours": round(minutes / 60, 1),
        "direct_cost": round(labor_cost + machine_cost, 2),
        "alerts": alerts,
        "orders": [order_summary(db, row) for row in sorted(active, key=lambda item: (item.priority, item.planned_end or date.max))[:12]],
        "lines": line_performance(db, company_id, start, end),
        "period": {"start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
    }


def build_alerts(db, company_id: int, orders: list) -> list[dict]:
    alerts = []
    for order in orders:
        if order.status not in {"completed", "cancelled"} and order.planned_end and order.planned_end < date.today():
            alerts.append({"type": "danger", "title": f"{order.order_no} fora do prazo", "detail": order.current_stage})
    low_lots = db.query(StockLot).filter(StockLot.company_id == company_id, StockLot.quantity <= StockLot.reserved).limit(5).all()
    alerts.extend({"type": "warning", "title": f"Lote {lot.lot_no} sem disponível", "detail": lot.location or "Stock"} for lot in low_lots)
    certs = db.query(Certification).filter(
        Certification.company_id == company_id,
        Certification.expiry_date <= date.today() + timedelta(days=30),
    ).limit(5).all()
    alerts.extend({"type": "warning", "title": f"Certificação {row.cert_type} a expirar", "detail": str(row.expiry_date)} for row in certs)
    machines = db.query(Machine).filter(
        Machine.company_id == company_id,
        Machine.next_maintenance <= date.today() + timedelta(days=7),
    ).limit(5).all()
    alerts.extend({"type": "info", "title": f"Manutenção: {row.name}", "detail": str(row.next_maintenance)} for row in machines)
    company = db.get(Company, company_id)
    outbox = list(dict((company.settings or {}).get("primavera") or {}).get("outbox") or []) if company else []
    stuck = [item for item in outbox if item.get("status") == "alert" or int(item.get("attempts") or 0) >= 3]
    if stuck:
        alerts.insert(0, {
            "type": "danger",
            "title": f"Primavera: {len(stuck)} documento(s) falharam 3 vezes",
            "detail": "ERP → Ligação Primavera · a fila deixou de tentar sozinha",
        })
    return alerts[:10]


def order_summary(db, order: ProductionOrder) -> dict:
    style = db.get(Style, order.style_id)
    return {
        "id": order.id, "order_no": order.order_no,
        "reference": style.reference if style else "", "description": style.description if style else "",
        "quantity": order.quantity, "completed": order.completed_quantity,
        "progress": round(order.completed_quantity / order.quantity * 100, 1) if order.quantity else 0,
        "stage": order.current_stage, "location": order.current_location,
        "planned_end": order.planned_end.isoformat() if order.planned_end else None,
        "status": order.status, "priority": order.priority,
    }


def line_performance(db, company_id: int, start: date | None = None, end: date | None = None) -> list[dict]:
    lines = db.query(ProductionLine).filter_by(company_id=company_id, active=True).all()
    earned_minutes = _earned_minutes_resolver(db, company_id)
    result = []
    for line in lines:
        events = [
            row for row in db.query(ProductionEvent).filter_by(company_id=company_id, line_id=line.id).all()
            if _in_period(row, start, end)
        ]
        minutes = sum(row.duration_minutes for row in events)
        good = sum(row.quantity_good for row in events)
        rejected = sum(row.quantity_rejected for row in events)
        earned = sum(earned_minutes(row) for row in events)
        efficiency = round(earned / minutes * 100, 1) if minutes else 0
        result.append({
            "id": line.id, "code": line.code, "name": line.name,
            "mode": line.production_mode, "good": good, "rejected": rejected,
            "hours": round(minutes / 60, 1), "efficiency": efficiency,
            "target": line.target_efficiency,
        })
    return result


def employee_performance(db, company_id: int, start: date | None = None, end: date | None = None) -> list[dict]:
    employees = db.query(Employee).filter_by(company_id=company_id, active=True).all()
    earned_minutes = _earned_minutes_resolver(db, company_id)
    rows = []
    for employee in employees:
        events = [
            row for row in db.query(ProductionEvent).filter_by(company_id=company_id, employee_id=employee.id).all()
            if _in_period(row, start, end)
        ]
        minutes = sum(event.duration_minutes for event in events)
        good = sum(event.quantity_good for event in events)
        rejected = sum(event.quantity_rejected for event in events)
        earned = sum(earned_minutes(event) for event in events)
        rows.append({
            "id": employee.id, "code": employee.code, "name": employee.name,
            "job_title": employee.job_title, "good": good, "rejected": rejected,
            "hours": round(minutes / 60, 2), "efficiency": round(earned / minutes * 100, 1) if minutes else 0,
            "labor_cost": round(sum(event.labor_cost for event in events), 2),
            "cost_per_good": round(sum(event.labor_cost for event in events) / good, 4) if good else 0,
        })
    return sorted(rows, key=lambda row: row["efficiency"], reverse=True)


def machine_performance(db, company_id: int, start: date | None = None, end: date | None = None) -> list[dict]:
    machines = db.query(Machine).filter_by(company_id=company_id, active=True).all()
    rows = []
    for machine in machines:
        events = [
            row for row in db.query(ProductionEvent).filter_by(company_id=company_id, machine_id=machine.id).all()
            if _in_period(row, start, end)
        ]
        minutes = sum(event.duration_minutes for event in events)
        good = sum(event.quantity_good for event in events)
        rejected = sum(event.quantity_rejected for event in events)
        performance = round(good / ((machine.target_units_hour or 0) * minutes / 60) * 100, 1) if machine.target_units_hour and minutes else 0
        quality = round(good / (good + rejected) * 100, 1) if good + rejected else 100
        rows.append({
            "id": machine.id, "code": machine.code, "name": machine.name,
            "type": machine.machine_type, "status": machine.status,
            "good": good, "rejected": rejected, "hours": round(minutes / 60, 2),
            "performance": performance, "quality": quality,
            "cost": round(sum(event.machine_cost for event in events), 2),
            "cost_per_good": round(sum(event.machine_cost for event in events) / good, 4) if good else 0,
        })
    return rows


def cost_overview(db, company_id: int) -> dict:
    events = db.query(ProductionEvent).filter_by(company_id=company_id).all()
    samples = db.query(Sample).filter_by(company_id=company_id).all()
    cutting = db.query(CuttingJob).filter_by(company_id=company_id).all()
    return {
        "labor": round(sum(row.labor_cost for row in events), 2),
        "machines": round(sum(row.machine_cost for row in events), 2),
        "samples": round(sum(row.total_cost for row in samples), 2),
        "cutting": round(sum(row.labor_cost + row.machine_cost for row in cutting), 2),
        "production_good": sum(row.quantity_good for row in events),
        "production_rejected": sum(row.quantity_rejected for row in events),
        "employee_rows": employee_performance(db, company_id),
        "machine_rows": machine_performance(db, company_id),
    }


def downtime_summary(db, company_id: int, start: date | None = None, end: date | None = None) -> dict:
    """Paragens por linha/motivo e um OEE aproximado a partir dos dados já
    recolhidos (Disponibilidade x Desempenho x Qualidade) - antes, DowntimeEvent
    era capturado no chão de fábrica e nunca lido em lado nenhum."""
    downtimes = [
        row for row in db.query(DowntimeEvent).filter_by(company_id=company_id).all()
        if (not start or (row.started_at and row.started_at.date() >= start))
        and (not end or (row.started_at and row.started_at.date() <= end))
    ]
    events = [row for row in db.query(ProductionEvent).filter_by(company_id=company_id).all() if _in_period(row, start, end)]
    earned_minutes = _earned_minutes_resolver(db, company_id)

    by_reason: dict[str, float] = {}
    by_line: dict[int, float] = {}
    for row in downtimes:
        by_reason[row.reason_code] = by_reason.get(row.reason_code, 0) + (row.duration_minutes or 0)
        if row.line_id:
            by_line[row.line_id] = by_line.get(row.line_id, 0) + (row.duration_minutes or 0)

    lines = db.query(ProductionLine).filter_by(company_id=company_id, active=True).all()
    line_rows = []
    for line in lines:
        line_events = [row for row in events if row.line_id == line.id]
        productive = sum(row.duration_minutes or 0 for row in line_events)
        downtime = by_line.get(line.id, 0)
        good = sum(row.quantity_good or 0 for row in line_events)
        rejected = sum(row.quantity_rejected or 0 for row in line_events)
        earned = sum(earned_minutes(row) for row in line_events)
        availability = productive / (productive + downtime) if (productive + downtime) else 0
        performance = min(1, earned / productive) if productive else 0
        quality = good / (good + rejected) if (good + rejected) else 1
        if not productive and not downtime:
            continue
        line_rows.append({
            "id": line.id, "name": line.name,
            "productive_minutes": round(productive, 1), "downtime_minutes": round(downtime, 1),
            "availability_pct": round(availability * 100, 1), "performance_pct": round(performance * 100, 1),
            "quality_pct": round(quality * 100, 1), "oee_pct": round(availability * performance * quality * 100, 1),
        })

    reason_rows = sorted(
        [{"reason_code": code, "label": DOWNTIME_REASON_LABEL.get(code, code), "minutes": round(minutes, 1)} for code, minutes in by_reason.items()],
        key=lambda row: row["minutes"], reverse=True,
    )
    return {
        "lines": line_rows,
        "reasons": reason_rows,
        "total_downtime_minutes": round(sum(by_reason.values()), 1),
        "event_count": len(downtimes),
    }
