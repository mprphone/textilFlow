from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import (
    Operation, ProcessJob, ProductOperation, ProductionOrder, ProductionRouteStep,
    QualityInspection, ServiceStage, SewingPlan, SubcontractJob, SubcontractService,
    WorkAssignment,
)

STEP_LABEL = {
    "cutting": "Corte", "sewing": "Confeção interna", "dyeing": "Tinturaria", "laundry": "Lavandaria",
    "printing": "Estamparia", "embroidery": "Bordado", "finishing": "Acabamento",
    "transport": "Transporte", "other": "Serviço externo",
    "operation": "Operação", "service_stage": "Etapa interna",
    "quality": "Qualidade / revista", "packing": "Embalagem", "shipping": "Expedição",
}
DONE_JOB = {"received", "cancelled"}
OPEN_JOB = {"planned", "sent", "partial", "problem"}


def route_for_style(db: Session, style_id: int | None) -> list[ProductionRouteStep]:
    if not style_id:
        return []
    return (
        db.query(ProductionRouteStep)
        .filter_by(style_id=style_id)
        .order_by(ProductionRouteStep.sequence)
        .all()
    )


def _cutting_progress(db: Session, order: ProductionOrder) -> dict:
    from .production_stage import _cutting_state
    state, job = _cutting_state(db, order)
    status = {"not_started": "not_started", "planned": "not_started", "in_progress": "in_progress", "completed": "done"}[state]
    good = float(job.good_pieces or 0) if job else 0.0
    return {"status": status, "quantity_sent": None, "quantity_received": good}


def _sewing_progress(db: Session, order: ProductionOrder) -> dict:
    plans = [
        plan for plan in db.query(SewingPlan).filter_by(production_order_id=order.id, company_id=order.company_id).all()
        if plan.allocation_type == "internal" and plan.status not in {"cancelled"} and (plan.quantity or 0) > 0
    ]
    produced = float(order.completed_quantity or 0)
    target = float(order.quantity or 0)
    if produced > 0.001 and target > 0 and produced >= target * 0.99:
        status = "done"
    elif plans or produced > 0.001:
        status = "in_progress"
    else:
        status = "not_started"
    return {"status": status, "quantity_sent": None, "quantity_received": produced}


def _subcontract_progress(db: Session, order: ProductionOrder, step: ProductionRouteStep, jobs: list[SubcontractJob]) -> dict:
    related = [job for job in jobs if job.chain_step_sequence == step.sequence]
    if not related:
        # fallback: sem job explicitamente ligado a este passo, tenta pelo servico
        related = [job for job in jobs if job.subcontract_service_id == step.subcontract_service_id]
    open_jobs = [job for job in related if job.status in OPEN_JOB]
    sent = round(sum(job.quantity or 0 for job in related if job.status != "cancelled"), 2)
    received = round(sum(job.accepted_quantity or 0 for job in related), 2)
    done = bool(related) and not open_jobs and all(job.status in DONE_JOB for job in related)
    if done:
        status = "done"
    elif related:
        status = "in_progress"
    else:
        status = "not_started"
    return {"status": status, "quantity_sent": sent, "quantity_received": received}


def _quantity_progress(value: float, target: float) -> dict:
    status = "done" if target > 0 and value + 0.001 >= target else "in_progress" if value > 0.001 else "not_started"
    return {"status": status, "quantity_sent": None, "quantity_received": round(value, 2)}


def step_progress(db: Session, order: ProductionOrder, step: ProductionRouteStep, jobs: list[SubcontractJob] | None = None) -> dict:
    if step.step_type == "cutting":
        return _cutting_progress(db, order)
    if step.step_type == "sewing":
        return _sewing_progress(db, order)
    if step.step_type == "operation":
        completed = sum(float(row.completed_quantity or 0) for row in db.query(WorkAssignment).filter_by(
            production_order_id=order.id, product_operation_id=step.product_operation_id
        ).all())
        return _quantity_progress(completed, float(order.quantity or 0))
    if step.step_type == "service_stage":
        stage = db.get(ServiceStage, step.service_stage_id) if step.service_stage_id else None
        rows = db.query(ProcessJob).filter_by(production_order_id=order.id, process_kind=stage.code).all() if stage else []
        return _quantity_progress(sum(float(row.completed_quantity or 0) for row in rows), float(order.quantity or 0))
    if step.step_type == "quality":
        rows = db.query(QualityInspection).filter_by(production_order_id=order.id).filter(
            QualityInspection.inspection_type.in_(["final", "revista"])
        ).all()
        released = sum(float(row.released_quantity or 0) for row in rows if row.result in {"passed", "conditional"})
        return _quantity_progress(released, float(order.quantity or 0))
    if step.step_type in {"packing", "shipping"}:
        from .execution import movement_holdings
        stock = movement_holdings(db, order)
        value = stock["finished_goods"] + stock["shipped"] if step.step_type == "packing" else stock["shipped"]
        return _quantity_progress(value, float(order.quantity or 0))
    jobs = jobs if jobs is not None else db.query(SubcontractJob).filter_by(production_order_id=order.id).all()
    return _subcontract_progress(db, order, step, jobs)


def _step_label(db: Session, step: ProductionRouteStep) -> str:
    if step.step_type in {"cutting", "sewing", "quality", "packing", "shipping"}:
        return STEP_LABEL[step.step_type]
    if step.step_type == "operation":
        product_step = db.get(ProductOperation, step.product_operation_id) if step.product_operation_id else None
        operation = db.get(Operation, product_step.operation_id) if product_step else None
        return operation.name if operation else STEP_LABEL["operation"]
    if step.step_type == "service_stage":
        stage = db.get(ServiceStage, step.service_stage_id) if step.service_stage_id else None
        return stage.name if stage else STEP_LABEL["service_stage"]
    service = db.get(SubcontractService, step.subcontract_service_id) if step.subcontract_service_id else None
    return service.name if service else STEP_LABEL.get("other")


def build_route_status(db: Session, order: ProductionOrder) -> list[dict]:
    """Sequencia completa (interna + externa) com estado e bloqueios, na ordem configurada."""
    steps = route_for_style(db, order.style_id)
    if not steps:
        return []
    jobs = db.query(SubcontractJob).filter_by(production_order_id=order.id).all()
    result = []
    previous_done = True
    previous_label = None
    for step in steps:
        progress = step_progress(db, order, step, jobs)
        locked = not previous_done
        kind = "external" if step.step_type == "subcontract" else "internal"
        label = _step_label(db, step)
        if locked:
            status = "locked"
            reason = f"Cadeado até concluir {previous_label}" if previous_label else None
            can_go = False
        elif progress["status"] == "in_progress":
            status, reason, can_go = "in_progress", None, True
        elif progress["status"] == "done":
            status, reason, can_go = "done", None, False
        else:
            status, reason, can_go = "ready", None, True
        result.append({
            "sequence": step.sequence,
            "key": step.step_type if step.step_type != "subcontract" else (
                _service_category(db, step) or "other"
            ),
            "label": label,
            "kind": kind,
            "step_type": step.step_type,
            "category": _service_category(db, step),
            "required": step.is_required,
            "notes": step.notes,
            "locked": locked,
            "status": status,
            "reason": reason,
            "can_distribute": can_go,
            "out_quantity": progress["quantity_sent"] or 0,
            "quantity_sent": progress["quantity_sent"] or 0,
            "quantity_received": progress["quantity_received"] or 0,
            "job_count": 0,
        })
        if step.is_required:
            previous_done = progress["status"] == "done"
        previous_label = label
    return result


def _service_category(db: Session, step: ProductionRouteStep) -> str | None:
    if step.step_type != "subcontract" or not step.subcontract_service_id:
        return None
    service = db.get(SubcontractService, step.subcontract_service_id)
    category = (service.category if service else "other") or "other"
    return category


def assign_route_step(db: Session, job: SubcontractJob, order: ProductionOrder | None = None) -> int | None:
    if job.chain_step_sequence:
        return job.chain_step_sequence
    order = order or (db.get(ProductionOrder, job.production_order_id) if job.production_order_id else None)
    if not order:
        return None
    steps = route_for_style(db, order.style_id)
    for step in steps:
        if step.step_type == "subcontract" and step.subcontract_service_id == job.subcontract_service_id:
            job.chain_step_sequence = step.sequence
            return step.sequence
    return None


def assert_route_ready(db: Session, order: ProductionOrder, *, step_type: str, subcontract_service_id: int | None = None, override: bool = False) -> dict:
    """Verifica se um passo (interno ou externo) pode avancar, segundo a rota configurada do artigo.

    Devolve {"ready": True} sem restricoes quando o artigo nao tem rota configurada
    (comportamento antigo mantido intacto via os gates legados).
    """
    steps = route_for_style(db, order.style_id)
    if not steps:
        return {"ready": True, "reason": ""}
    target = next(
        (s for s in steps if s.step_type == step_type and (step_type != "subcontract" or s.subcontract_service_id == subcontract_service_id)),
        None,
    )
    if not target:
        if step_type == "subcontract":
            return {"ready": False, "reason": "Este serviço não faz parte da sequência definida para este artigo."}
        return {"ready": True, "reason": ""}
    previous_required = [s for s in steps if s.sequence < target.sequence and s.is_required]
    if not previous_required:
        return {"ready": True, "reason": ""}
    jobs = db.query(SubcontractJob).filter_by(production_order_id=order.id).all()
    for prev in previous_required:
        progress = step_progress(db, order, prev, jobs)
        if progress["status"] != "done":
            label = _step_label(db, prev)
            return {"ready": override, "reason": f"Passo anterior ({label}) ainda não está concluído."}
    return {"ready": True, "reason": ""}
