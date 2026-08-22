from datetime import date, timedelta

from sqlalchemy import func

from ..models import (
    Certification, Company, CuttingJob, Employee, Machine, Operation, ProductionEvent,
    ProductionLine, ProductionOrder, QualityInspection, Sample, StockLot, Style,
)


def dashboard_metrics(db, company_id: int) -> dict:
    orders = db.query(ProductionOrder).filter_by(company_id=company_id).all()
    events = db.query(ProductionEvent).filter_by(company_id=company_id).all()
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
        "lines": line_performance(db, company_id),
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


def line_performance(db, company_id: int) -> list[dict]:
    lines = db.query(ProductionLine).filter_by(company_id=company_id, active=True).all()
    result = []
    for line in lines:
        events = db.query(ProductionEvent).filter_by(company_id=company_id, line_id=line.id).all()
        minutes = sum(row.duration_minutes for row in events)
        good = sum(row.quantity_good for row in events)
        rejected = sum(row.quantity_rejected for row in events)
        earned = 0
        for event in events:
            operation = db.get(Operation, event.operation_id) if event.operation_id else None
            earned += (operation.standard_time_min if operation else 0) * event.quantity_good
        efficiency = round(earned / minutes * 100, 1) if minutes else 0
        result.append({
            "id": line.id, "code": line.code, "name": line.name,
            "mode": line.production_mode, "good": good, "rejected": rejected,
            "hours": round(minutes / 60, 1), "efficiency": efficiency,
            "target": line.target_efficiency,
        })
    return result


def employee_performance(db, company_id: int) -> list[dict]:
    employees = db.query(Employee).filter_by(company_id=company_id, active=True).all()
    rows = []
    for employee in employees:
        events = db.query(ProductionEvent).filter_by(company_id=company_id, employee_id=employee.id).all()
        minutes = sum(event.duration_minutes for event in events)
        good = sum(event.quantity_good for event in events)
        rejected = sum(event.quantity_rejected for event in events)
        earned = sum((db.get(Operation, event.operation_id).standard_time_min if event.operation_id and db.get(Operation, event.operation_id) else 0) * event.quantity_good for event in events)
        rows.append({
            "id": employee.id, "code": employee.code, "name": employee.name,
            "job_title": employee.job_title, "good": good, "rejected": rejected,
            "hours": round(minutes / 60, 2), "efficiency": round(earned / minutes * 100, 1) if minutes else 0,
            "labor_cost": round(sum(event.labor_cost for event in events), 2),
            "cost_per_good": round(sum(event.labor_cost for event in events) / good, 4) if good else 0,
        })
    return sorted(rows, key=lambda row: row["efficiency"], reverse=True)


def machine_performance(db, company_id: int) -> list[dict]:
    machines = db.query(Machine).filter_by(company_id=company_id, active=True).all()
    rows = []
    for machine in machines:
        events = db.query(ProductionEvent).filter_by(company_id=company_id, machine_id=machine.id).all()
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
