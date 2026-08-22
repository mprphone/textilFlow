from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Operation, ProductOperation, ProductionBatch, ProductionLine, ProductionOrder, WorkAssignment


KANBAN_WAITING = "waiting"
KANBAN_PULLED = "pulled"
KANBAN_IN_SEWING = "in_sewing"
KANBAN_DONE = "done"


def line_wip_status(db: Session, line: ProductionLine) -> dict:
    if not line:
        return {"wip": 0, "limit": 0, "can_pull": False, "batches": []}
    batches = (
        db.query(ProductionBatch)
        .filter_by(company_id=line.company_id, sewing_line_id=line.id)
        .filter(ProductionBatch.kanban_status.in_({KANBAN_PULLED, KANBAN_IN_SEWING}))
        .all()
    )
    wip = sum(batch.quantity or 0 for batch in batches)
    limit = line.wip_limit or 0
    return {
        "wip": wip,
        "limit": limit,
        "can_pull": limit == 0 or wip < limit,
        "batches": [
            {"id": batch.id, "batch_no": batch.batch_no, "quantity": batch.quantity, "status": batch.kanban_status}
            for batch in batches
        ],
    }


def next_waiting_batches(db: Session, company_id: int, line_id: int | None = None, order_id: int | None = None, limit: int = 5) -> list[ProductionBatch]:
    query = (
        db.query(ProductionBatch)
        .filter_by(company_id=company_id, kanban_status=KANBAN_WAITING)
    )
    if line_id:
        query = query.filter_by(sewing_line_id=line_id)
    if order_id:
        query = query.filter_by(production_order_id=order_id)
    return query.order_by(ProductionBatch.id).limit(limit).all()


def request_next_batch(db: Session, company_id: int, line_id: int, order_id: int | None = None) -> ProductionBatch | None:
    line = db.get(ProductionLine, line_id)
    if not line or line.company_id != company_id:
        raise ValueError("Linha de confeção inválida")
    if not line.kanban_pull_enabled:
        raise ValueError("Esta linha não tem sinal kanban ativo")
    status = line_wip_status(db, line)
    if not status["can_pull"]:
        raise ValueError(f"WIP limit atingido ({status['wip']}/{status['limit']}). Conclua ou liberte lotes antes de puxar mais.")
    batches = next_waiting_batches(db, company_id, line_id=line_id, order_id=order_id, limit=1)
    if not batches:
        batches = next_waiting_batches(db, company_id, order_id=order_id, limit=1)
    if not batches:
        return None
    batch = batches[0]
    batch.sewing_line_id = line_id
    batch.kanban_status = KANBAN_PULLED
    batch.current_location = f"Linha {line.code} (kanban puxado)"
    batch.updated_at = datetime.now(timezone.utc)
    db.flush()
    return batch


def _create_sewing_assignment(db: Session, batch: ProductionBatch, line: ProductionLine) -> WorkAssignment | None:
    order = db.get(ProductionOrder, batch.production_order_id) if batch.production_order_id else None
    if not order:
        return None
    product_operation = (
        db.query(ProductOperation)
        .filter_by(style_id=order.style_id)
        .order_by(ProductOperation.sequence, ProductOperation.id)
        .first()
    )
    operation = db.get(Operation, product_operation.operation_id) if product_operation else None
    if not operation:
        operation = db.query(Operation).filter_by(company_id=batch.company_id).order_by(Operation.id).first()
    if not operation:
        return None
    assignment = WorkAssignment(
        company_id=batch.company_id,
        production_order_id=order.id,
        batch_id=batch.id,
        product_operation_id=product_operation.id if product_operation else None,
        operation_id=operation.id,
        line_id=line.id,
        planned_quantity=batch.quantity or 0,
        standard_minutes=(product_operation.smv or 0) * (batch.quantity or 0) if product_operation else 0,
        status="in_progress",
        notes="Gerado pelo kanban corte→costura",
    )
    db.add(assignment)
    db.flush()
    return assignment


def release_batch_to_sewing(db: Session, company_id: int, batch_id: int, line_id: int) -> ProductionBatch:
    batch = db.get(ProductionBatch, batch_id)
    if not batch or batch.company_id != company_id:
        raise ValueError("Lote não encontrado")
    line = db.get(ProductionLine, line_id)
    if not line or line.company_id != company_id:
        raise ValueError("Linha inválida")
    if batch.kanban_status not in {KANBAN_WAITING, KANBAN_PULLED}:
        raise ValueError(f"Lote não pode ser libertado: estado {batch.kanban_status}")
    batch.sewing_line_id = line_id
    batch.kanban_status = KANBAN_IN_SEWING
    batch.current_location = f"Linha {line.code}"
    batch.status = "in_progress"
    batch.updated_at = datetime.now(timezone.utc)
    db.flush()
    _create_sewing_assignment(db, batch, line)
    return batch


def complete_sewing_batch(db: Session, company_id: int, batch_id: int, quantity: float | None = None) -> ProductionBatch:
    batch = db.get(ProductionBatch, batch_id)
    if not batch or batch.company_id != company_id:
        raise ValueError("Lote não encontrado")
    if batch.kanban_status != KANBAN_IN_SEWING:
        raise ValueError("Só lotes em costura podem ser concluídos")
    done_qty = quantity if quantity is not None else (batch.quantity or 0)
    batch.completed_quantity = min(batch.quantity or 0, done_qty)
    batch.kanban_status = KANBAN_DONE
    batch.status = "completed" if batch.completed_quantity >= (batch.quantity or 0) - 0.001 else "in_progress"
    batch.current_location = "Acabamento / Expedição"
    batch.updated_at = datetime.now(timezone.utc)
    order = db.get(ProductionOrder, batch.production_order_id) if batch.production_order_id else None
    if order:
        order.completed_quantity = min(
            order.quantity or 0,
            sum(
                b.completed_quantity or 0
                for b in db.query(ProductionBatch).filter_by(production_order_id=order.id).all()
            ),
        )
    for assignment in db.query(WorkAssignment).filter_by(batch_id=batch.id, status="in_progress").all():
        assignment.completed_quantity = batch.completed_quantity
        assignment.status = "completed" if batch.status == "completed" else "in_progress"
    db.flush()
    return batch


def kanban_board(db: Session, company_id: int) -> dict:
    lines = db.query(ProductionLine).filter_by(company_id=company_id, active=True).all()
    columns = []
    for line in lines:
        if not line.kanban_pull_enabled:
            continue
        status = line_wip_status(db, line)
        waiting = next_waiting_batches(db, company_id, line_id=line.id, limit=20)
        columns.append({
            "line_id": line.id,
            "line_code": line.code,
            "line_name": line.name,
            "wip_limit": line.wip_limit,
            "wip": status["wip"],
            "can_pull": status["can_pull"],
            "pulled": status["batches"],
            "waiting": [
                {"id": batch.id, "batch_no": batch.batch_no, "quantity": batch.quantity, "order_id": batch.production_order_id}
                for batch in waiting
            ],
        })
    waiting_pool = [
        {"id": batch.id, "batch_no": batch.batch_no, "quantity": batch.quantity, "order_id": batch.production_order_id}
        for batch in next_waiting_batches(db, company_id, limit=50)
    ]
    return {"lines": columns, "waiting_pool": waiting_pool}
