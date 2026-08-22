from collections import defaultdict
from datetime import date, datetime, time, timezone

from fastapi import HTTPException

from ..models import (
    Employee, Machine, Operation, ProductOperation, ProductionBatch, ProductionEvent,
    ProductionLine, ProductionOrder, SalesOrder, SalesOrderLine, Style, WorkAssignment,
)
from .production_stage import dispatch_ready_status, ensure_final_quality_checkpoint, update_order_stage


def employee_hourly_rate(employee) -> float:
    if not employee:
        return 0.0
    if employee.hourly_cost:
        return float(employee.hourly_cost)
    salary = float(employee.monthly_salary or 0)
    weekly = float(employee.weekly_hours or 40) or 40
    if salary <= 0:
        return 0.0
    return round(salary / (weekly * 52 / 12), 4)


def refresh_employee_rate(employee) -> None:
    salary = float(getattr(employee, "monthly_salary", 0) or 0)
    weekly = float(employee.weekly_hours or 40) or 40
    if salary > 0:
        employee.hourly_cost = round(salary / (weekly * 52 / 12), 4)


def register_output(db, assignment: WorkAssignment, payload, *, occurred_on: date | None = None) -> ProductionEvent:
    employee = db.get(Employee, assignment.employee_id) if assignment.employee_id else None
    machine = db.get(Machine, assignment.machine_id) if assignment.machine_id else None
    minutes = payload.duration_minutes or 0
    if assignment.planned_quantity and not getattr(payload, "allow_overage", False):
        prospective = (assignment.completed_quantity or 0) + (assignment.rejected_quantity or 0) + payload.quantity_good + payload.quantity_rejected
        if prospective > assignment.planned_quantity + 0.001:
            raise HTTPException(
                422,
                f"Isto ultrapassa a quantidade planeada desta atribuição ({assignment.planned_quantity:.0f} un.). "
                "Confirme para registar mesmo assim (ex.: retrabalho).",
            )
    rate = employee_hourly_rate(employee)
    event = ProductionEvent(
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        production_order_id=assignment.production_order_id,
        batch_id=assignment.batch_id,
        operation_id=assignment.operation_id,
        employee_id=assignment.employee_id,
        machine_id=assignment.machine_id,
        line_id=assignment.line_id,
        event_type=payload.event_type,
        duration_minutes=minutes,
        quantity_good=payload.quantity_good,
        quantity_rejected=payload.quantity_rejected,
        labor_cost=round((rate / 60) * minutes, 4),
        machine_cost=round(((machine.hourly_cost if machine else 0) / 60) * minutes, 4),
        notes=payload.notes,
        source=payload.source,
        event_time=datetime.combine(occurred_on, time(12, 0), tzinfo=timezone.utc) if occurred_on else datetime.now(timezone.utc),
    )
    db.add(event)
    assignment.completed_quantity += payload.quantity_good
    assignment.rejected_quantity += payload.quantity_rejected
    assignment.actual_minutes += minutes
    assignment.status = "completed" if assignment.completed_quantity >= assignment.planned_quantity else "in_progress"

    if assignment.batch_id:
        batch = db.get(ProductionBatch, assignment.batch_id)
        if batch:
            batch.current_operation_id = assignment.operation_id
            batch.current_location = f"Linha {assignment.line_id}" if assignment.line_id else batch.current_location
            batch.completed_quantity = min(batch.quantity or 0, round((batch.completed_quantity or 0) + payload.quantity_good, 2))
            batch.status = "completed" if batch.quantity and batch.completed_quantity >= batch.quantity * 0.99 else "in_progress"

    order = db.get(ProductionOrder, assignment.production_order_id)
    if order:
        # Agrupa por operacao antes de tirar o minimo: varias atribuicoes da
        # mesma operacao (ex.: dois operadores no registo diario) tem de somar
        # a sua producao, nao ser comparadas isoladamente contra o total da OF.
        assignments = db.query(WorkAssignment).filter_by(production_order_id=order.id).all()
        by_operation = defaultdict(lambda: [0.0, 0.0])
        for row in assignments:
            if not row.planned_quantity:
                continue
            entry = by_operation[row.operation_id]
            entry[0] += row.completed_quantity or 0
            entry[1] += row.planned_quantity or 0
        ratios = [min(1, completed / planned) for completed, planned in by_operation.values() if planned]
        progress = min(ratios) if ratios else 0
        order.completed_quantity = round(order.quantity * progress, 2)
        order.status = "completed" if progress >= 1 else "in_progress"
        update_order_stage(db, order)
        if not order.actual_start:
            order.actual_start = datetime.now(timezone.utc)
        if progress >= 1:
            order.actual_end = datetime.now(timezone.utc)
            ensure_final_quality_checkpoint(db, order)
        if order.sales_order_line_id:
            sales_line = db.get(SalesOrderLine, order.sales_order_line_id)
            sales_order = db.get(SalesOrder, sales_line.sales_order_id) if sales_line else None
            if sales_order and sales_order.status not in {"ready", "shipped", "cancelled"}:
                if dispatch_ready_status(db, sales_order)["ready"]:
                    sales_order.status = "ready"
    if machine:
        if assignment.status == "completed":
            still_active = db.query(WorkAssignment.id).filter(
                WorkAssignment.machine_id == machine.id,
                WorkAssignment.status.in_(["queued", "in_progress"]),
                WorkAssignment.id != assignment.id,
            ).first()
            machine.status = "available" if not still_active else "running"
        else:
            machine.status = "running"
    db.flush()
    return event


def _first_operation(db, order: ProductionOrder):
    routing = db.query(ProductOperation).filter_by(style_id=order.style_id).order_by(ProductOperation.sequence, ProductOperation.id).first() if order.style_id else None
    if routing and routing.operation_id:
        return routing.operation_id, routing.id
    operation = db.query(Operation).filter_by(company_id=order.company_id).order_by(Operation.id).first()
    if not operation:
        raise HTTPException(422, "Configure pelo menos uma operação em Configurar a fábrica → Operações e tempos.")
    return operation.id, None


def list_daily_output(db, company_id: int, work_date: date) -> dict:
    start = datetime.combine(work_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(work_date, time.max, tzinfo=timezone.utc)
    rows = db.query(ProductionEvent).filter(
        ProductionEvent.company_id == company_id,
        ProductionEvent.event_type == "output",
        ProductionEvent.event_time >= start,
        ProductionEvent.event_time <= end,
    ).order_by(ProductionEvent.id.desc()).all()
    items = []
    for event in rows:
        order = db.get(ProductionOrder, event.production_order_id)
        employee = db.get(Employee, event.employee_id) if event.employee_id else None
        line = db.get(ProductionLine, event.line_id) if event.line_id else None
        style = db.get(Style, order.style_id) if order and order.style_id else None
        items.append({
            "id": event.id,
            "order_no": order.order_no if order else "—",
            "article": style.reference if style else "",
            "employee": employee.name if employee else "—",
            "hourly_cost": employee_hourly_rate(employee),
            "line": line.name if line else "—",
            "quantity_good": event.quantity_good,
            "quantity_rejected": event.quantity_rejected,
            "hours": round((event.duration_minutes or 0) / 60, 2),
            "labor_cost": event.labor_cost,
        })
    missing = [
        {"id": row.id, "name": row.name}
        for row in db.query(Employee).filter_by(company_id=company_id, active=True).all()
        if employee_hourly_rate(row) <= 0
    ]
    return {
        "date": work_date.isoformat(),
        "items": items,
        "totals": {
            "quantity_good": round(sum(row["quantity_good"] or 0 for row in items), 2),
            "hours": round(sum(row["hours"] or 0 for row in items), 2),
            "labor_cost": round(sum(row["labor_cost"] or 0 for row in items), 2),
        },
        "missing_salary": missing,
    }


def record_daily_output(db, company_id: int, payload: dict) -> dict:
    work_date = date.fromisoformat(str(payload.get("work_date") or date.today().isoformat())[:10])
    order = db.get(ProductionOrder, int(payload.get("production_order_id") or 0))
    employee = db.get(Employee, int(payload.get("employee_id") or 0))
    if not order or order.company_id != company_id:
        raise HTTPException(404, "Ordem de fabrico não encontrada")
    if not employee or employee.company_id != company_id:
        raise HTTPException(404, "Funcionário não encontrado")
    if employee_hourly_rate(employee) <= 0:
        raise HTTPException(422, f"Indique o vencimento de {employee.name} em Configurar a fábrica → Pessoas, para calcular o custo real.")
    line_id = payload.get("line_id") or employee.line_id or order.line_id
    hours = float(payload.get("hours") or 8)
    if hours <= 0:
        raise HTTPException(422, "Indique as horas trabalhadas neste dia")
    good = float(payload.get("quantity_good") or 0)
    rejected = float(payload.get("quantity_rejected") or 0)
    if good <= 0 and rejected <= 0:
        raise HTTPException(422, "Indique as peças produzidas")
    operation_id, product_operation_id = _first_operation(db, order)
    assignment = db.query(WorkAssignment).filter_by(
        company_id=company_id,
        production_order_id=order.id,
        employee_id=employee.id,
        operation_id=operation_id,
    ).order_by(WorkAssignment.id.desc()).first()
    if not assignment:
        # Reparte a quantidade planeada pelo que ainda falta desta operacao,
        # nao pela quantidade total da OF — senao, com varios operadores na
        # mesma operacao, cada atribuicao infla o denominador do progresso.
        same_operation = db.query(WorkAssignment).filter_by(
            company_id=company_id, production_order_id=order.id, operation_id=operation_id,
        ).all()
        already_planned = sum(row.planned_quantity or 0 for row in same_operation)
        remaining = max(0.0, (order.quantity or 0) - already_planned) or good
        product_op = db.get(ProductOperation, product_operation_id) if product_operation_id else None
        operation = db.get(Operation, operation_id)
        smv = (product_op.smv if product_op else 0) or (operation.standard_time_min if operation else 0) or 0
        assignment = WorkAssignment(
            company_id=company_id,
            production_order_id=order.id,
            operation_id=operation_id,
            product_operation_id=product_operation_id,
            employee_id=employee.id,
            line_id=line_id,
            planned_quantity=remaining,
            standard_minutes=round(smv * remaining, 2),
            status="in_progress",
        )
        db.add(assignment)
        db.flush()
    else:
        assignment.employee_id = employee.id
        assignment.line_id = line_id or assignment.line_id
    class _Payload:
        quantity_good = good
        quantity_rejected = rejected
        duration_minutes = round(hours * 60, 2)
        event_type = "output"
        notes = payload.get("notes") or f"Produção do dia {work_date.isoformat()}"
        source = "daily"
        allow_overage = bool(payload.get("allow_overage"))
    event = register_output(db, assignment, _Payload(), occurred_on=work_date)
    db.flush()
    return {"ok": True, "event_id": event.id, "labor_cost": event.labor_cost, **list_daily_output(db, company_id, work_date)}

