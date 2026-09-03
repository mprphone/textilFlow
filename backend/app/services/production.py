from collections import defaultdict
from datetime import date, datetime, time, timezone

from fastapi import HTTPException

from ..models import (
    Customer, Employee, Machine, Operation, ProductOperation, ProductionBatch, ProductionEvent,
    ProductionLine, ProductionMovement, ProductionOrder, ProductionOrderVariant, SalesOrder, SalesOrderLine,
    Style, StyleVariant, WorkAssignment,
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


def _routing_progress(db, order: ProductionOrder, assignments: list[WorkAssignment]) -> float:
    """Avanco da OF pelo gargalo da sequencia, incluindo passos ainda sem atribuicao."""
    routing = (
        db.query(ProductOperation)
        .filter_by(style_id=order.style_id)
        .order_by(ProductOperation.sequence, ProductOperation.id)
        .all()
    )
    if routing:
        completed_by_step = defaultdict(float)
        for row in assignments:
            if row.product_operation_id:
                completed_by_step[row.product_operation_id] += float(row.completed_quantity or 0)
        target = float(order.quantity or 0)
        if target <= 0:
            return 0
        return min(min(1.0, completed_by_step[step.id] / target) for step in routing)

    by_operation = defaultdict(lambda: [0.0, 0.0])
    for row in assignments:
        if not row.planned_quantity:
            continue
        entry = by_operation[row.operation_id]
        entry[0] += row.completed_quantity or 0
        entry[1] += row.planned_quantity or 0
    ratios = [min(1, completed / planned) for completed, planned in by_operation.values() if planned]
    return min(ratios) if ratios else 0


def _refresh_batch_progress(db, batch: ProductionBatch) -> None:
    assignments = db.query(WorkAssignment).filter_by(batch_id=batch.id).all()
    if not assignments:
        return
    order = db.get(ProductionOrder, batch.production_order_id)
    routing = db.query(ProductOperation).filter_by(style_id=order.style_id).all() if order else []
    if routing:
        completed_by_step = defaultdict(float)
        for row in assignments:
            if row.product_operation_id:
                completed_by_step[row.product_operation_id] += float(row.completed_quantity or 0)
        ratios = [min(1.0, completed_by_step[step.id] / float(batch.quantity or 1)) for step in routing]
        progress = min(ratios) if ratios else 0
        batch.completed_quantity = round(float(batch.quantity or 0) * progress, 2)
    else:
        by_operation = defaultdict(float)
        for row in assignments:
            by_operation[row.operation_id] += float(row.completed_quantity or 0)
        batch.completed_quantity = min(float(batch.quantity or 0), min(by_operation.values())) if by_operation else 0
    batch.status = "completed" if batch.quantity and batch.completed_quantity >= batch.quantity * 0.99 else "in_progress"


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
    # Quando a OF já usa transferências formais entre operações, uma operação
    # posterior não pode declarar mais saída do que recebeu da anterior.
    if assignment.product_operation_id and not getattr(payload, "allow_overage", False):
        routing = db.query(ProductOperation).filter_by(style_id=db.get(ProductionOrder, assignment.production_order_id).style_id).order_by(ProductOperation.sequence, ProductOperation.id).all()
        position = next((index for index, row in enumerate(routing) if row.id == assignment.product_operation_id), 0)
        transfers = db.query(ProductionMovement).filter_by(production_order_id=assignment.production_order_id, movement_type="operation_transfer").all()
        if position > 0 and transfers:
            received = sum(float(row.quantity or 0) for row in transfers if int((row.metadata_json or {}).get("target_product_operation_id") or 0) == assignment.product_operation_id)
            related = db.query(WorkAssignment).filter_by(production_order_id=assignment.production_order_id, product_operation_id=assignment.product_operation_id).all()
            consumed = sum(float(row.completed_quantity or 0) + float(row.rejected_quantity or 0) for row in related)
            incoming = float(payload.quantity_good or 0) + float(payload.quantity_rejected or 0)
            if consumed + incoming > received + 0.001:
                raise HTTPException(422, f"Esta operação recebeu apenas {received:g} unidades da operação anterior.")
    rate = employee_hourly_rate(employee)
    event = ProductionEvent(
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        production_order_id=assignment.production_order_id,
        batch_id=assignment.batch_id,
        variant_id=getattr(payload, "variant_id", None),
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
        energy_cost=round(float(getattr(payload, "energy_cost", 0) or 0), 4),
        consumables_cost=round(float(getattr(payload, "consumables_cost", 0) or 0), 4),
        setup_cost=round(float(getattr(payload, "setup_cost", 0) or 0), 4),
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
            _refresh_batch_progress(db, batch)

    order = db.get(ProductionOrder, assignment.production_order_id)
    if order:
        assignments = db.query(WorkAssignment).filter_by(production_order_id=order.id).all()
        progress = _routing_progress(db, order, assignments)
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
            if sales_order and sales_order.status not in {"ready", "partially_shipped", "shipped", "cancelled"}:
                linked_lines = db.query(SalesOrderLine).filter_by(sales_order_id=sales_order.id).all()
                complete = all(
                    sum(float(item.completed_quantity or 0) for item in db.query(ProductionOrder).filter_by(sales_order_line_id=line.id).all())
                    + 0.001 >= float(line.quantity or 0)
                    for line in linked_lines
                )
                sales_order.status = "ready" if complete else "in_production"
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
    from .execution import sync_output_movement
    sync_output_movement(db, event, assignment)
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
        variant = db.get(StyleVariant, event.variant_id) if event.variant_id else None
        items.append({
            "id": event.id,
            "order_no": order.order_no if order else "—",
            "article": style.reference if style else "",
            "employee": employee.name if employee else "",
            "variant_id": event.variant_id,
            "size": variant.size if variant else "Único",
            "color": variant.color if variant else "",
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


def daily_output_options(db, company_id: int) -> dict:
    """Build the order → article → size catalogue for the tablet workflow."""
    lines = db.query(ProductionLine).filter_by(company_id=company_id, active=True).order_by(ProductionLine.name).all()
    production_orders = db.query(ProductionOrder).filter(
        ProductionOrder.company_id == company_id,
        ~ProductionOrder.status.in_(["completed", "cancelled"]),
    ).order_by(ProductionOrder.priority.desc(), ProductionOrder.planned_end, ProductionOrder.id.desc()).all()

    reported = defaultdict(float)
    events = db.query(ProductionEvent).filter_by(company_id=company_id, event_type="output").all()
    for event in events:
        reported[(event.production_order_id, event.variant_id)] += float(event.quantity_good or 0)

    grouped = {}
    for order in production_orders:
        style = db.get(Style, order.style_id) if order.style_id else None
        sales_line = db.get(SalesOrderLine, order.sales_order_line_id) if order.sales_order_line_id else None
        sales_order = db.get(SalesOrder, sales_line.sales_order_id) if sales_line else None
        customer = db.get(Customer, sales_order.customer_id) if sales_order and sales_order.customer_id else None
        line = db.get(ProductionLine, order.line_id) if order.line_id else None

        if sales_order:
            group_key = f"sales-{sales_order.id}"
            group_no = sales_order.order_no
            delivery_date = sales_order.delivery_date
        else:
            group_key = f"production-{order.id}"
            group_no = order.order_no
            delivery_date = order.planned_end

        group = grouped.setdefault(group_key, {
            "key": group_key,
            "order_no": group_no,
            "customer": customer.name if customer else "Produção interna",
            "delivery_date": delivery_date.isoformat() if delivery_date else None,
            "articles": [],
        })

        order_variants = db.query(ProductionOrderVariant).filter_by(production_order_id=order.id).all()
        variants = []
        if order_variants:
            for order_variant in order_variants:
                variant = db.get(StyleVariant, order_variant.variant_id)
                if not variant:
                    continue
                done = reported[(order.id, variant.id)]
                planned = float(order_variant.quantity or 0)
                variants.append({
                    "variant_id": variant.id,
                    "sku": variant.sku,
                    "color": variant.color or "",
                    "size": variant.size or "Único",
                    "planned_quantity": planned,
                    "reported_quantity": round(done, 2),
                    "remaining_quantity": round(max(0, planned - done), 2),
                })
        else:
            style_variants = db.query(StyleVariant).filter_by(
                company_id=company_id, style_id=order.style_id, active=True,
            ).order_by(StyleVariant.id).all()
            if style_variants:
                for variant in style_variants:
                    done = reported[(order.id, variant.id)]
                    variants.append({
                        "variant_id": variant.id,
                        "sku": variant.sku,
                        "color": variant.color or "",
                        "size": variant.size or "Único",
                        "planned_quantity": None,
                        "reported_quantity": round(done, 2),
                        "remaining_quantity": None,
                    })
            else:
                done = reported[(order.id, None)]
                planned = float(order.quantity or 0)
                variants.append({
                    "variant_id": None,
                    "sku": "",
                    "color": "",
                    "size": "Único",
                    "planned_quantity": planned,
                    "reported_quantity": round(done, 2),
                    "remaining_quantity": round(max(0, planned - done), 2),
                })

        variant_done = sum(float(item["reported_quantity"] or 0) for item in variants)
        article_done = max(float(order.completed_quantity or 0), variant_done)
        group["articles"].append({
            "production_order_id": order.id,
            "order_no": order.order_no,
            "reference": style.reference if style else order.order_no,
            "description": (sales_line.description if sales_line and sales_line.description else None)
                or (style.description if style else ""),
            "line_id": order.line_id,
            "line": line.name if line else "",
            "planned_quantity": float(order.quantity or 0),
            "reported_quantity": round(article_done, 2),
            "remaining_quantity": round(max(0, float(order.quantity or 0) - article_done), 2),
            "variants": variants,
        })

    orders = list(grouped.values())
    for group in orders:
        group["planned_quantity"] = round(sum(item["planned_quantity"] for item in group["articles"]), 2)
        group["reported_quantity"] = round(sum(item["reported_quantity"] for item in group["articles"]), 2)
        group["remaining_quantity"] = round(sum(item["remaining_quantity"] for item in group["articles"]), 2)
    orders.sort(key=lambda item: (item["delivery_date"] or "9999-12-31", item["order_no"]))
    return {
        "orders": orders,
        "lines": [{"id": row.id, "name": row.name, "code": row.code} for row in lines],
    }


def _record_daily_output_event(db, company_id: int, payload: dict) -> ProductionEvent:
    work_date = date.fromisoformat(str(payload.get("work_date") or date.today().isoformat())[:10])
    order = db.get(ProductionOrder, int(payload.get("production_order_id") or 0))
    employee_id = int(payload.get("employee_id") or 0) or None
    employee = db.get(Employee, employee_id) if employee_id else None
    if not order or order.company_id != company_id:
        raise HTTPException(404, "Ordem de fabrico não encontrada")
    if employee_id and (not employee or employee.company_id != company_id):
        raise HTTPException(404, "Funcionário não encontrado")
    if employee and employee_hourly_rate(employee) <= 0:
        raise HTTPException(422, f"Indique o vencimento de {employee.name} em Configurar a fábrica → Pessoas, para calcular o custo real.")

    line_id = int(payload.get("line_id") or (employee.line_id if employee else 0) or order.line_id or 0) or None
    line = db.get(ProductionLine, line_id) if line_id else None
    if not employee and not line:
        raise HTTPException(422, "Escolha a linha de produção")
    if line and (line.company_id != company_id or not line.active):
        raise HTTPException(422, "A linha de produção escolhida não está disponível")
    hours = float(payload.get("hours") or 0)
    if employee and hours <= 0:
        raise HTTPException(422, "Indique as horas trabalhadas neste dia")
    good = float(payload.get("quantity_good") or 0)
    rejected = float(payload.get("quantity_rejected") or 0)
    if good <= 0 and rejected <= 0:
        raise HTTPException(422, "Indique as peças produzidas")

    variant_id = int(payload.get("variant_id") or 0) or None
    order_grid = db.query(ProductionOrderVariant).filter_by(production_order_id=order.id).all()
    if variant_id:
        variant = db.get(StyleVariant, variant_id)
        if not variant or variant.company_id != company_id or variant.style_id != order.style_id:
            raise HTTPException(422, "O tamanho escolhido não pertence a este artigo")
        allowed = {row.variant_id for row in order_grid}
        if allowed and variant_id not in allowed:
            raise HTTPException(422, "O tamanho escolhido não pertence a esta encomenda")
    daily_events = db.query(ProductionEvent).filter(
        ProductionEvent.company_id == company_id,
        ProductionEvent.production_order_id == order.id,
        ProductionEvent.event_type == "output",
        ProductionEvent.source.in_(["daily", "daily-tablet"]),
    ).all()
    if order_grid and variant_id:
        planned = next(float(row.quantity or 0) for row in order_grid if row.variant_id == variant_id)
        already_done = sum(float(row.quantity_good or 0) for row in daily_events if row.variant_id == variant_id)
        if planned > 0 and already_done + good > planned + 0.001:
            remaining = max(0, planned - already_done)
            raise HTTPException(422, f"Neste tamanho faltam apenas {remaining:g} peças")
    elif not order_grid and order.quantity:
        already_done = max(
            float(order.completed_quantity or 0),
            sum(float(row.quantity_good or 0) for row in daily_events),
        )
        if already_done + good > float(order.quantity) + 0.001:
            remaining = max(0, float(order.quantity) - already_done)
            raise HTTPException(422, f"Nesta ordem faltam apenas {remaining:g} peças")

    # Serializa o procurar/criar da atribuição de linha (no-op no SQLite dos testes).
    db.query(ProductionOrder).filter_by(id=order.id).with_for_update().first()
    operation_id, product_operation_id = _first_operation(db, order)
    assignment = db.query(WorkAssignment).filter_by(
        company_id=company_id,
        production_order_id=order.id,
        employee_id=employee_id,
        line_id=line_id,
        operation_id=operation_id,
    ).order_by(WorkAssignment.id.desc()).first()
    if not assignment:
        if employee:
            same_operation = db.query(WorkAssignment).filter_by(
                company_id=company_id, production_order_id=order.id, operation_id=operation_id,
            ).all()
            already_planned = sum(row.planned_quantity or 0 for row in same_operation)
            planned = max(0.0, (order.quantity or 0) - already_planned) or good
        else:
            # A produção no tablet pertence à linha; a atribuição pode receber
            # todos os tamanhos da OF sem criar uma pessoa fictícia.
            planned = max(float(order.quantity or 0), good + rejected)
        product_op = db.get(ProductOperation, product_operation_id) if product_operation_id else None
        operation = db.get(Operation, operation_id)
        smv = (product_op.smv if product_op else 0) or (operation.standard_time_min if operation else 0) or 0
        assignment = WorkAssignment(
            company_id=company_id,
            production_order_id=order.id,
            operation_id=operation_id,
            product_operation_id=product_operation_id,
            employee_id=employee_id,
            line_id=line_id,
            planned_quantity=planned,
            standard_minutes=round(smv * planned, 2),
            status="in_progress",
        )
        db.add(assignment)
        db.flush()

    class _Payload:
        quantity_good = good
        quantity_rejected = rejected
        duration_minutes = round(hours * 60, 2)
        event_type = "output"
        notes = payload.get("notes") or f"Produção do dia {work_date.isoformat()}"
        source = "daily-tablet" if not employee else "daily"
        allow_overage = bool(payload.get("allow_overage"))

    _Payload.variant_id = variant_id
    return register_output(db, assignment, _Payload(), occurred_on=work_date)


def record_daily_output(db, company_id: int, payload: dict) -> dict:
    event = _record_daily_output_event(db, company_id, payload)
    db.flush()
    work_date = date.fromisoformat(str(payload.get("work_date") or date.today().isoformat())[:10])
    return {"ok": True, "event_id": event.id, "labor_cost": event.labor_cost, **list_daily_output(db, company_id, work_date)}


def record_daily_output_bulk(db, company_id: int, payload: dict) -> dict:
    work_date = date.fromisoformat(str(payload.get("work_date") or date.today().isoformat())[:10])
    order_id = int(payload.get("production_order_id") or 0)
    outputs = payload.get("outputs") or []
    if not outputs:
        raise HTTPException(422, "Escolha pelo menos um tamanho e indique a quantidade")

    seen = set()
    event_ids = []
    for output in outputs:
        variant_id = int(output.get("variant_id") or 0) or None
        if variant_id in seen:
            raise HTTPException(422, "O mesmo tamanho foi enviado mais do que uma vez")
        seen.add(variant_id)
        event = _record_daily_output_event(db, company_id, {
            "work_date": work_date.isoformat(),
            "production_order_id": order_id,
            "line_id": payload.get("line_id"),
            "variant_id": variant_id,
            "quantity_good": output.get("quantity_good"),
            "quantity_rejected": 0,
            "hours": 0,
            "notes": payload.get("notes"),
        })
        event_ids.append(event.id)
    db.flush()
    result = list_daily_output(db, company_id, work_date)
    return {"ok": True, "event_ids": event_ids, **result}
