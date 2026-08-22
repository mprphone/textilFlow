from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models import ProductOperation, ProductionLine, ProductionOrder, SewingPlan, SubcontractJob, SubcontractService
from .production_stage import assert_subcontract_ready, update_order_stage


ACTIVE_PLAN = {"planned", "released", "in_progress", "confirmed"}
OUT_JOB = {"planned", "sent", "partial", "problem"}


def job_out(job: SubcontractJob) -> float:
    if job.status not in OUT_JOB:
        return 0
    if job.status == "partial":
        return max(0, (job.quantity or 0) - (job.accepted_quantity or 0) - (job.rejected_quantity or 0))
    return max(0, job.quantity or 0)


def shipped_qty(order: ProductionOrder) -> float:
    return float((order.custom_data or {}).get("shipped_quantity") or 0)


def internal_plans(db: Session, order: ProductionOrder) -> list[SewingPlan]:
    return [
        plan for plan in db.query(SewingPlan).filter_by(production_order_id=order.id, company_id=order.company_id).all()
        if plan.allocation_type == "internal"
        and plan.status in ACTIVE_PLAN
        and plan.line_id
        and (plan.quantity or 0) > 0
    ]


def holdings(db: Session, order: ProductionOrder, jobs: list[SubcontractJob] | None = None) -> dict:
    jobs = jobs if jobs is not None else db.query(SubcontractJob).filter_by(production_order_id=order.id).all()
    plans = internal_plans(db, order)
    external = sum(job_out(job) for job in jobs)
    internal = sum(plan.quantity or 0 for plan in plans)
    shipped = shipped_qty(order)
    total = order.quantity or 0
    unassigned = max(0, total - internal - external - shipped)
    return {
        "internal": internal,
        "external": external,
        "shipped": shipped,
        "unassigned": unassigned,
        "total": total,
        "plans": plans,
    }


def _sam(db: Session, style_id: int) -> float:
    total = sum((row.smv or 0) for row in db.query(ProductOperation).filter_by(style_id=style_id).all())
    return round(total, 4) if total > 0 else 1


def _reduce_internal(plans: list[SewingPlan], quantity: float) -> None:
    remaining = quantity
    for plan in sorted(plans, key=lambda row: row.quantity or 0, reverse=True):
        if remaining <= 0:
            break
        take = min(plan.quantity or 0, remaining)
        plan.quantity = round((plan.quantity or 0) - take, 2)
        if plan.quantity <= 0:
            plan.status = "cancelled"
            plan.quantity = 0
        remaining = round(remaining - take, 2)
    if remaining > 0.001:
        raise ValueError("Não há quantidade suficiente na confeção interna")


def _add_internal(db: Session, order: ProductionOrder, line_id: int, quantity: float) -> SewingPlan:
    from .production_route import assert_route_ready, route_for_style
    if route_for_style(db, order.style_id):
        ready = assert_route_ready(db, order, step_type="sewing")
        if not ready["ready"]:
            raise ValueError(ready["reason"])
    line = db.get(ProductionLine, line_id)
    if not line or line.company_id != order.company_id:
        raise ValueError("Linha de confeção inválida")
    existing = next((plan for plan in internal_plans(db, order) if plan.line_id == line_id), None)
    if existing:
        existing.quantity = round((existing.quantity or 0) + quantity, 2)
        existing.status = "in_progress"
        order.line_id = line_id
        return existing
    start = date.today()
    sam = _sam(db, order.style_id)
    seq = db.query(SewingPlan).filter_by(company_id=order.company_id).count() + 1
    plan = SewingPlan(
        company_id=order.company_id,
        code=f"DIST-{order.order_no}-{seq:03d}",
        production_order_id=order.id,
        style_id=order.style_id,
        line_id=line_id,
        source_type="confirmed",
        allocation_type="internal",
        start_date=start,
        end_date=order.planned_end or (start + timedelta(days=7)),
        quantity=quantity,
        sam_minutes=sam,
        efficiency_pct=100,
        required_minutes=round(quantity * sam, 2),
        probability_pct=100,
        priority=order.priority or 3,
        status="in_progress",
        notes="Distribuído no controlo da produção",
    )
    db.add(plan)
    order.line_id = line_id
    order.current_stage = "confeção"
    order.status = "in_progress"
    return plan


def _add_subcontract(db: Session, order: ProductionOrder, service_id: int, quantity: float, override: bool = False) -> SubcontractJob:
    service = db.get(SubcontractService, service_id)
    if not service or service.company_id != order.company_id or not service.active:
        raise ValueError("Serviço subcontratado inválido")
    ready = assert_subcontract_ready(db, order, service, override=override)
    if not ready["ready"]:
        raise ValueError(ready["reason"])
    from .production_route import assert_route_ready, route_for_style
    route = route_for_style(db, order.style_id)
    step_sequence = None
    if route:
        route_ready = assert_route_ready(db, order, step_type="subcontract", subcontract_service_id=service_id, override=override)
        if not route_ready["ready"]:
            raise ValueError(route_ready["reason"])
        step_sequence = next((s.sequence for s in route if s.step_type == "subcontract" and s.subcontract_service_id == service_id), None)
        if step_sequence is None:
            raise ValueError(f"O serviço {service.code} não faz parte da sequência de produção definida para este artigo.")
    prefix = date.today().strftime("EXT-%Y%m%d-")
    n = db.query(SubcontractJob).filter(SubcontractJob.company_id == order.company_id, SubcontractJob.reference.like(f"{prefix}%")).count() + 1
    sent = date.today()
    expected = sent + timedelta(days=int(service.lead_time_days or 0)) if service.lead_time_days else None
    job = SubcontractJob(
        company_id=order.company_id,
        production_order_id=order.id,
        subcontract_service_id=service.id,
        supplier_id=service.supplier_id,
        chain_step_sequence=step_sequence,
        reference=f"{prefix}{n:03d}",
        quantity=quantity,
        unit=service.unit or "un",
        unit_cost=service.unit_cost or 0,
        planned_cost=round(quantity * (service.unit_cost or 0), 4),
        sent_date=sent,
        expected_date=expected,
        status="sent",
        notes=f"Distribuído a partir da OF {order.order_no}",
    )
    db.add(job)
    db.flush()
    update_order_stage(db, order)
    return job


def distribute(db: Session, order: ProductionOrder, payload: dict) -> dict:
    quantity = float(payload.get("quantity") or 0)
    if quantity <= 0:
        raise ValueError("Indique uma quantidade a distribuir")
    source = payload.get("source") or "unassigned"
    destination = payload.get("destination")
    if source == destination:
        raise ValueError("A origem e o destino não podem ser iguais")
    if destination not in {"internal", "subcontract", "shipped"}:
        raise ValueError("Destino inválido")
    if source not in {"unassigned", "internal"}:
        raise ValueError("Origem inválida")
    from .order_followup import assert_can_distribute
    assert_can_distribute(db, order, payload)

    stock = holdings(db, order)
    if source == "unassigned" and quantity > stock["unassigned"] + 0.001:
        raise ValueError(f"Só há {stock['unassigned']:.0f} por distribuir")
    if source == "internal":
        if quantity > stock["internal"] + 0.001:
            raise ValueError(f"Só há {stock['internal']:.0f} na confeção interna")
        _reduce_internal(stock["plans"], quantity)

    if destination == "internal":
        line_id = int(payload.get("line_id") or 0)
        if not line_id:
            raise ValueError("Escolha a linha de confeção")
        _add_internal(db, order, line_id, quantity)
    elif destination == "subcontract":
        service_id = int(payload.get("subcontract_service_id") or 0)
        if not service_id:
            raise ValueError("Escolha o serviço e o fornecedor")
        _add_subcontract(db, order, service_id, quantity)
    else:
        # `completed_quantity` representa produção real (peças confecionadas) e só
        # é escrito por register_output/register de eventos — aqui só se regista o
        # que já saiu para o cliente, para não haver dois escritores a anular-se.
        data = dict(order.custom_data or {})
        new_shipped = round(shipped_qty(order) + quantity, 2)
        data["shipped_quantity"] = new_shipped
        order.custom_data = data
        produced = order.completed_quantity or 0
        target = order.quantity or 0
        if produced >= target * 0.99 > 0 and stock["external"] <= 0:
            order.current_stage = "shipping"
            order.status = "completed" if new_shipped >= target - 0.001 else order.status

    db.commit()
    db.refresh(order)
    stock = holdings(db, order)
    return {
        "order_id": order.id,
        "holdings": {key: stock[key] for key in ("internal", "external", "shipped", "unassigned", "total")},
    }
