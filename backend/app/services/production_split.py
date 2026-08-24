from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models import (
    ProductOperation, ProductionBatch, ProductionLine, ProductionOrder, SalesOrder, SalesOrderLine,
    SewingPlan, StyleVariant, SubcontractJob, SubcontractService,
)
from .production_stage import assert_subcontract_ready, update_order_stage


ACTIVE_PLAN = {"planned", "released", "in_progress", "confirmed"}
OUT_JOB = {"planned", "sent", "partial", "problem"}


def job_out(job: SubcontractJob) -> float:
    if job.status not in OUT_JOB:
        return 0
    if job.status == "partial":
        return max(0, (job.quantity or 0) - (job.accepted_quantity or 0) - (job.rejected_quantity or 0))
    return max(0, job.quantity or 0)


def _advance_sales_order_status(db: Session, order: ProductionOrder) -> None:
    """Ao distribuir trabalho para produção (interna ou subcontrato), a encomenda
    de cliente ligada avança automaticamente para 'em produção' — mas só a partir
    de um estado inicial (nunca recua um estado mais avançado, ex. já expedido)."""
    if not order.sales_order_line_id:
        return
    line = db.get(SalesOrderLine, order.sales_order_line_id)
    if not line:
        return
    sales_order = db.get(SalesOrder, line.sales_order_id)
    if sales_order and sales_order.status in {"draft", "confirmed"}:
        sales_order.status = "in_production"


def shipped_qty(order: ProductionOrder) -> float:
    from .execution import movement_holdings
    db = getattr(order, "_sa_instance_state", None).session if getattr(order, "_sa_instance_state", None) else None
    return movement_holdings(db, order)["shipped"] if db else 0.0


def revista_qty(order: ProductionOrder) -> float:
    from .execution import movement_holdings
    db = getattr(order, "_sa_instance_state", None).session if getattr(order, "_sa_instance_state", None) else None
    if not db:
        return 0.0
    physical = movement_holdings(db, order)["revista"]
    data = order.custom_data or {}
    legacy = max(0.0, float(data.get("revista_quantity") or 0) - float(data.get("packed_quantity") or 0))
    return round(max(physical, legacy), 2)


def _add_revista(order: ProductionOrder, quantity: float) -> None:
    data = dict(order.custom_data or {})
    data["revista_quantity"] = round(revista_qty(order) + quantity, 2)
    order.custom_data = data


def _reduce_revista(order: ProductionOrder, quantity: float) -> None:
    current = revista_qty(order)
    if quantity > current + 0.001:
        raise ValueError(f"Só há {current:.0f} na revista")
    data = dict(order.custom_data or {})
    data["revista_quantity"] = round(current - quantity, 2)
    order.custom_data = data


def internal_plans(db: Session, order: ProductionOrder) -> list[SewingPlan]:
    return [
        plan for plan in db.query(SewingPlan).filter_by(production_order_id=order.id, company_id=order.company_id).all()
        if plan.allocation_type == "internal"
        and plan.status in ACTIVE_PLAN
        and plan.line_id
        and (plan.quantity or 0) > 0
    ]


def holdings(db: Session, order: ProductionOrder, jobs: list[SubcontractJob] | None = None) -> dict:
    from .execution import movement_holdings
    return {**movement_holdings(db, order), "plans": internal_plans(db, order)}


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


def _add_internal(
    db: Session, order: ProductionOrder, line_id: int, quantity: float,
    planned_date: date | None = None, batch_id: int | None = None,
    variant_id: int | None = None,
) -> SewingPlan:
    from .production_route import assert_route_ready, route_for_style
    if route_for_style(db, order.style_id):
        ready = assert_route_ready(db, order, step_type="sewing")
        if not ready["ready"]:
            raise ValueError(ready["reason"])
    line = db.get(ProductionLine, line_id)
    if not line or line.company_id != order.company_id:
        raise ValueError("Linha de confeção inválida")
    existing = next((
        plan for plan in internal_plans(db, order)
        if plan.line_id == line_id and plan.batch_id == batch_id and plan.variant_id == variant_id
    ), None)
    if existing:
        existing.quantity = round((existing.quantity or 0) + quantity, 2)
        existing.status = "in_progress"
        order.line_id = line_id
        if planned_date:
            existing.start_date = planned_date
        return existing
    start = planned_date or date.today()
    sam = _sam(db, order.style_id)
    from .sequences import next_value
    seq = next_value(db, order.company_id, "sewing_plan")
    plan = SewingPlan(
        company_id=order.company_id,
        code=f"DIST-{order.order_no}-{seq:03d}",
        production_order_id=order.id,
        batch_id=batch_id,
        variant_id=variant_id,
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
    order.status = "in_progress"
    from .production_stage import update_order_stage
    update_order_stage(db, order)
    return plan


def _add_subcontract(
    db: Session, order: ProductionOrder, service_id: int, quantity: float,
    override: bool = False, planned_date: date | None = None,
    batch_id: int | None = None, variant_id: int | None = None,
) -> SubcontractJob:
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
    from .sequences import formatted
    reference = formatted(
        db, order.company_id, "subcontract", prefix=prefix, width=3,
        period=date.today().strftime("%Y%m%d"),
    )
    sent = planned_date or date.today()
    expected = sent + timedelta(days=int(service.lead_time_days or 0)) if service.lead_time_days else None
    job = SubcontractJob(
        company_id=order.company_id,
        production_order_id=order.id,
        batch_id=batch_id,
        variant_id=variant_id,
        subcontract_service_id=service.id,
        supplier_id=service.supplier_id,
        chain_step_sequence=step_sequence,
        reference=reference,
        quantity=quantity,
        unit=service.unit or "un",
        unit_cost=service.unit_cost or 0,
        planned_cost=round(quantity * (service.unit_cost or 0), 4),
        sent_date=sent,
        expected_date=expected,
        status="sent",
        notes=f"Distribuído a partir da OF {order.order_no}" + (" · excepção à sequência" if override else ""),
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
    if destination not in {"internal", "subcontract", "shipped", "revista"}:
        raise ValueError("Destino inválido")
    if source not in {"unassigned", "internal", "revista"}:
        raise ValueError("Origem inválida")
    # Bloqueia a OF durante toda a operacao de leitura+validacao+escrita, para
    # dois pedidos de distribuicao concorrentes nao passarem ambos a mesma
    # validacao de saldo antes de qualquer um escrever (no-op no SQLite).
    db.query(ProductionOrder).filter_by(id=order.id).with_for_update().first()
    override = bool(payload.get("override") or payload.get("exception"))
    planned_date_raw = payload.get("planned_date")
    planned_date = date.fromisoformat(str(planned_date_raw)[:10]) if planned_date_raw else None
    batch_id = int(payload.get("batch_id") or 0) or None
    variant_id = int(payload.get("variant_id") or 0) or None
    if batch_id:
        batch = db.get(ProductionBatch, batch_id)
        if not batch or batch.company_id != order.company_id or batch.production_order_id != order.id:
            raise ValueError("O lote não pertence a esta ordem de fabrico")
        variant_id = variant_id or batch.variant_id
        if batch.variant_id and variant_id != batch.variant_id:
            raise ValueError("A variante não corresponde ao lote selecionado")
    if variant_id:
        variant = db.get(StyleVariant, variant_id)
        if not variant or variant.company_id != order.company_id or variant.style_id != order.style_id:
            raise ValueError("A variante não pertence ao artigo desta ordem")
    from .order_followup import assert_can_distribute
    assert_can_distribute(db, order, payload, override=override)

    stock = holdings(db, order)
    if source == "unassigned" and quantity > stock["unassigned"] + 0.001:
        raise ValueError(f"Só há {stock['unassigned']:.0f} por distribuir")
    if source == "internal":
        if quantity > stock["internal"] + 0.001:
            raise ValueError(f"Só há {stock['internal']:.0f} na confeção interna")
        _reduce_internal(stock["plans"], quantity)
    if source == "revista":
        _reduce_revista(order, quantity)

    subcontract_job_id = None
    if destination == "internal":
        line_id = int(payload.get("line_id") or 0)
        if not line_id:
            raise ValueError("Escolha a linha de confeção")
        _add_internal(db, order, line_id, quantity, planned_date=planned_date, batch_id=batch_id, variant_id=variant_id)
    elif destination == "subcontract":
        service_id = int(payload.get("subcontract_service_id") or 0)
        if not service_id:
            raise ValueError("Escolha o serviço e o fornecedor")
        job = _add_subcontract(db, order, service_id, quantity, override=override, planned_date=planned_date, batch_id=batch_id, variant_id=variant_id)
        subcontract_job_id = job.id
    if destination in {"internal", "subcontract"}:
        _advance_sales_order_status(db, order)
    elif destination == "revista":
        _add_revista(order, quantity)
        update_order_stage(db, order)
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
        update_order_stage(db, order)
        if produced >= target * 0.99 > 0 and stock["external"] <= 0 and new_shipped >= target - 0.001:
            order.status = "completed"

    # A transacao e controlada pelo endpoint chamador para que o movimento e o
    # respetivo documento sejam confirmados (ou anulados) em conjunto.
    db.flush()
    from .execution import record_movement
    movement = record_movement(
        db, company_id=order.company_id, production_order_id=order.id,
        batch_id=batch_id, variant_id=variant_id,
        movement_type="distribution", quantity=quantity,
        location_from=source, location_to=destination,
        reference=payload.get("reference"), user_id=payload.get("user_id"),
        metadata={"line_id": payload.get("line_id"), "subcontract_job_id": subcontract_job_id},
    )
    stock = holdings(db, order)
    return {
        "order_id": order.id,
        "holdings": {key: stock[key] for key in ("internal", "external", "shipped", "revista", "finished_goods", "unassigned", "total")},
        "subcontract_job_id": subcontract_job_id,
        "movement_id": movement.id,
    }
