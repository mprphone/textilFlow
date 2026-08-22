from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import ProductionOrder, SubcontractChainStep, SubcontractJob, SubcontractService, Style


def chain_steps_for_style(db: Session, style_id: int | None) -> list[SubcontractChainStep]:
    if not style_id:
        return []
    return (
        db.query(SubcontractChainStep)
        .filter_by(style_id=style_id)
        .order_by(SubcontractChainStep.sequence)
        .all()
    )


def assign_chain_step(db: Session, job: SubcontractJob, order: ProductionOrder | None = None) -> int | None:
    if job.chain_step_sequence:
        return job.chain_step_sequence
    order = order or db.get(ProductionOrder, job.production_order_id) if job.production_order_id else None
    if not order:
        return None
    steps = chain_steps_for_style(db, order.style_id)
    if not steps:
        return None
    service_id = job.subcontract_service_id
    for step in steps:
        if step.subcontract_service_id == service_id:
            job.chain_step_sequence = step.sequence
            return step.sequence
    return None


def assert_chain_ready(db: Session, order: ProductionOrder, step_sequence: int | None, *, override: bool = False) -> dict:
    if not order or not step_sequence:
        return {"ready": True, "reason": ""}
    steps = chain_steps_for_style(db, order.style_id)
    if not steps:
        return {"ready": True, "reason": ""}
    previous_steps = [step for step in steps if step.sequence < step_sequence and step.is_required]
    if not previous_steps:
        return {"ready": True, "reason": ""}
    jobs = db.query(SubcontractJob).filter_by(production_order_id=order.id).all()
    jobs_by_step: dict[int, list[SubcontractJob]] = {}
    for job in jobs:
        if job.chain_step_sequence:
            jobs_by_step.setdefault(job.chain_step_sequence, []).append(job)
    for prev in previous_steps:
        prev_jobs = jobs_by_step.get(prev.sequence, [])
        if not prev_jobs:
            return {
                "ready": override,
                "reason": f"Passo anterior {prev.sequence} ainda não foi enviado.",
            }
        if not all(job.status in {"received", "cancelled"} for job in prev_jobs):
            open_jobs = [job for job in prev_jobs if job.status not in {"received", "cancelled"}]
            return {
                "ready": override,
                "reason": f"Passo anterior {prev.sequence} ainda não regressou ({len(open_jobs)} envio aberto).",
            }
    return {"ready": True, "reason": ""}


def build_chain_status(db: Session, order: ProductionOrder) -> list[dict]:
    steps = chain_steps_for_style(db, order.style_id)
    if not steps:
        return []
    jobs = db.query(SubcontractJob).filter_by(production_order_id=order.id).all()
    jobs_by_step: dict[int, list[SubcontractJob]] = {}
    for job in jobs:
        if job.chain_step_sequence:
            jobs_by_step.setdefault(job.chain_step_sequence, []).append(job)
    result = []
    for step in steps:
        step_jobs = jobs_by_step.get(step.sequence, [])
        service = db.get(SubcontractService, step.subcontract_service_id)
        open_count = sum(1 for job in step_jobs if job.status not in {"received", "cancelled"})
        done = bool(step_jobs) and all(job.status in {"received", "cancelled"} for job in step_jobs)
        result.append({
            "sequence": step.sequence,
            "service_id": step.subcontract_service_id,
            "service_name": service.name if service else "—",
            "service_code": service.code if service else "—",
            "category": service.category if service else "other",
            "required": step.is_required,
            "notes": step.notes,
            "jobs": [job.id for job in step_jobs],
            "quantity_sent": sum(job.quantity or 0 for job in step_jobs if job.status not in {"cancelled"}),
            "quantity_received": sum(job.accepted_quantity or 0 for job in step_jobs),
            "status": "done" if done else "in_progress" if step_jobs else "pending",
            "locked": open_count > 0 and not done,
        })
    return result


def previous_step_summary(db: Session, order: ProductionOrder, step_sequence: int) -> str | None:
    check = assert_chain_ready(db, order, step_sequence)
    if check["ready"]:
        return None
    return check["reason"]
