from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models import (
    BatchGenealogy, Operation, ProductOperation, ProductionBatch, ProductionMovement,
    ProductionOrder, QualityInspection, StyleVariant, WorkAssignment,
)
from .serialization import model_to_dict


EPSILON = 0.001
PHYSICAL_MOVEMENT_TYPES = {
    "order_release", "distribution", "operation_transfer", "subcontract_receipt",
    "packing", "shipment", "return_receipt", "rework_start", "rework_complete", "scrap",
    "return_disposition",
}


def record_movement(
    db: Session, *, company_id: int, production_order_id: int, movement_type: str,
    quantity: float, location_to: str, location_from: str | None = None,
    batch_id: int | None = None, variant_id: int | None = None,
    product_operation_id: int | None = None, quality_inspection_id: int | None = None,
    shipment_id: int | None = None, reference: str | None = None,
    finished_goods_unit_id: int | None = None, rework_order_id: int | None = None,
    customer_return_id: int | None = None,
    idempotency_key: str | None = None, metadata: dict | None = None,
    user_id: int | None = None,
) -> ProductionMovement:
    if idempotency_key:
        existing = db.query(ProductionMovement).filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return existing
    row = ProductionMovement(
        company_id=company_id, production_order_id=production_order_id,
        batch_id=batch_id, variant_id=variant_id, product_operation_id=product_operation_id,
        quality_inspection_id=quality_inspection_id, shipment_id=shipment_id,
        finished_goods_unit_id=finished_goods_unit_id, rework_order_id=rework_order_id,
        customer_return_id=customer_return_id,
        movement_type=movement_type, quantity=round(float(quantity or 0), 2),
        location_from=location_from, location_to=location_to,
        reference=reference, idempotency_key=idempotency_key,
        metadata_json=metadata or {}, user_id=user_id,
    )
    db.add(row)
    db.flush()
    return row


def ensure_opening_movement(db: Session, order: ProductionOrder) -> ProductionMovement:
    return record_movement(
        db, company_id=order.company_id, production_order_id=order.id,
        movement_type="order_release", quantity=order.quantity,
        location_to="unassigned", reference=order.order_no,
        idempotency_key=f"order-release:{order.id}",
    )


def _location_bucket(location: str | None) -> str | None:
    value = (location or "").lower()
    if not value:
        return None
    if value in {"unassigned", "received_external"}:
        return "unassigned"
    if value in {"internal", "production"} or value.startswith(("operation:", "batch:", "linha ")):
        return "internal"
    if value == "subcontract" or value.startswith("subcontract:"):
        return "external"
    if value in {"revista", "quality_inspection", "quality_approved"}:
        return "revista"
    if value in {"finished_goods", "warehouse"}:
        return "finished_goods"
    if value == "shipped":
        return "shipped"
    if value in {"quarantine", "rework", "scrap", "second_quality"}:
        return value
    return None


def movement_holdings(db: Session, order: ProductionOrder) -> dict:
    ensure_opening_movement(db, order)
    balances = {key: 0.0 for key in ("unassigned", "internal", "external", "revista", "finished_goods", "shipped", "quarantine", "rework", "scrap", "second_quality")}
    movements = db.query(ProductionMovement).filter_by(production_order_id=order.id).order_by(ProductionMovement.id).all()
    for movement in movements:
        if movement.movement_type not in PHYSICAL_MOVEMENT_TYPES:
            continue
        quantity = float(movement.quantity or 0)
        source = _location_bucket(movement.location_from)
        target = _location_bucket(movement.location_to)
        if source:
            balances[source] -= quantity
        if target:
            balances[target] += quantity
    for key in balances:
        balances[key] = round(max(0.0, balances[key]), 2)
    balances["packed"] = balances["finished_goods"] + balances["shipped"]
    balances["total"] = round(sum(balances[key] for key in ("unassigned", "internal", "external", "revista", "finished_goods", "shipped", "quarantine", "rework", "scrap", "second_quality")), 2)
    return balances


def backfill_execution_ledger(db: Session) -> int:
    """Abre o livro e converte saldos legados uma única vez por OF."""
    from ..models import SewingPlan, SubcontractJob
    count = 0
    for order in db.query(ProductionOrder).all():
        if db.query(ProductionMovement.id).filter_by(idempotency_key=f"order-release:{order.id}").first():
            continue
        ensure_opening_movement(db, order)
        internal = sum(float(row.quantity or 0) for row in db.query(SewingPlan).filter_by(production_order_id=order.id, allocation_type="internal").filter(SewingPlan.status.notin_(["cancelled", "completed", "backlog"])).all())
        external = sum(max(0.0, float(row.quantity or 0) - float(row.accepted_quantity or 0) - float(row.rejected_quantity or 0)) for row in db.query(SubcontractJob).filter_by(production_order_id=order.id).filter(SubcontractJob.status.in_(["planned", "sent", "partial", "problem"])).all())
        shipped = float((order.custom_data or {}).get("shipped_quantity") or 0)
        packed = float((order.custom_data or {}).get("packed_quantity") or 0)
        revista_total = float((order.custom_data or {}).get("revista_quantity") or 0)
        finished = max(0.0, packed - shipped)
        revista = max(0.0, revista_total - packed)
        allocated = 0.0
        # Estados terminais têm prioridade. Nos dados antigos, os acumulados de
        # confeção/revista podiam ainda incluir peças já embaladas ou expedidas.
        for destination, quantity in (("shipped", shipped), ("finished_goods", finished), ("revista", revista), ("subcontract", external), ("internal", internal)):
            take = min(max(0.0, float(order.quantity or 0) - allocated), max(0.0, quantity))
            if take <= EPSILON:
                continue
            record_movement(db, company_id=order.company_id, production_order_id=order.id, movement_type="distribution", quantity=take, location_from="unassigned", location_to=destination, reference="Migração de saldo inicial", idempotency_key=f"legacy-balance:{order.id}:{destination}")
            allocated += take
        count += 1
    db.flush()
    return count


def sync_output_movement(db: Session, event, assignment: WorkAssignment) -> None:
    if abs(float(event.quantity_good or 0)) > EPSILON:
        record_movement(
            db, company_id=event.company_id, production_order_id=event.production_order_id,
            batch_id=event.batch_id, product_operation_id=assignment.product_operation_id,
            movement_type="operation_output", quantity=event.quantity_good,
            location_to=f"operation:{assignment.product_operation_id or assignment.operation_id}:output",
            reference=f"Evento #{event.id}", idempotency_key=f"production-event:{event.id}:good",
            metadata={"assignment_id": assignment.id, "operation_id": assignment.operation_id},
        )
    if abs(float(event.quantity_rejected or 0)) > EPSILON:
        record_movement(
            db, company_id=event.company_id, production_order_id=event.production_order_id,
            batch_id=event.batch_id, product_operation_id=assignment.product_operation_id,
            movement_type="quality_reject", quantity=event.quantity_rejected,
            location_from=f"operation:{assignment.product_operation_id or assignment.operation_id}:output",
            location_to="quarantine", reference=f"Evento #{event.id}",
            idempotency_key=f"production-event:{event.id}:reject",
            metadata={"assignment_id": assignment.id, "operation_id": assignment.operation_id},
        )


def _routing(db: Session, order: ProductionOrder) -> list[ProductOperation]:
    return db.query(ProductOperation).filter_by(style_id=order.style_id).order_by(ProductOperation.sequence, ProductOperation.id).all()


def operation_flow(db: Session, order: ProductionOrder) -> dict:
    routing = _routing(db, order)
    assignments = db.query(WorkAssignment).filter_by(production_order_id=order.id).all()
    movements = db.query(ProductionMovement).filter_by(production_order_id=order.id).all()
    steps = []
    for index, step in enumerate(routing):
        operation = db.get(Operation, step.operation_id)
        related = [row for row in assignments if row.product_operation_id == step.id]
        produced = round(sum(float(row.completed_quantity or 0) for row in related), 2)
        rejected = round(sum(float(row.rejected_quantity or 0) for row in related), 2)
        transfers = [row for row in movements if row.movement_type == "operation_transfer" and row.product_operation_id == step.id]
        transferred = round(sum(float(row.quantity or 0) for row in transfers), 2)
        received = round(sum(
            float(row.quantity or 0) for row in movements
            if row.movement_type == "operation_transfer"
            and int((row.metadata_json or {}).get("target_product_operation_id") or 0) == step.id
        ), 2)
        # completed_quantity já contém apenas peças boas; rejeições são
        # informativas e não devem ser abatidas uma segunda vez.
        available = max(0.0, round(produced - transferred, 2))
        next_step = routing[index + 1] if index + 1 < len(routing) else None
        steps.append({
            **model_to_dict(step), "operation_code": operation.code if operation else None,
            "operation_name": operation.name if operation else None,
            "produced_quantity": produced, "rejected_quantity": rejected,
            "received_quantity": received, "transferred_quantity": transferred,
            "available_to_transfer": available,
            "next_product_operation_id": next_step.id if next_step else None,
            "destination": f"operation:{next_step.id}:input" if next_step else "revista",
            "status": "completed" if produced + EPSILON >= float(order.quantity or 0)
            else "in_progress" if produced > EPSILON or received > EPSILON else "waiting",
        })
    return {"order": model_to_dict(order), "steps": steps, "movements": [model_to_dict(row) for row in movements[-100:]]}


def transfer_operation(db: Session, order: ProductionOrder, payload: dict, user_id: int | None = None) -> dict:
    source_id = int(payload.get("product_operation_id") or 0)
    quantity = round(float(payload.get("quantity") or 0), 2)
    if quantity <= EPSILON:
        raise ValueError("Indique uma quantidade a transferir")
    flow = operation_flow(db, order)
    source = next((row for row in flow["steps"] if row["id"] == source_id), None)
    if not source:
        raise ValueError("Operação não pertence à sequência desta OF")
    if quantity > source["available_to_transfer"] + EPSILON:
        raise ValueError(f"Só existem {source['available_to_transfer']:g} unidades disponíveis nesta operação")
    target_id = source["next_product_operation_id"]
    location_to = source["destination"]
    movement = record_movement(
        db, company_id=order.company_id, production_order_id=order.id,
        batch_id=payload.get("batch_id"), variant_id=payload.get("variant_id"),
        product_operation_id=source_id, movement_type="operation_transfer", quantity=quantity,
        location_from=f"operation:{source_id}:output", location_to=location_to,
        reference=payload.get("reference") or f"TRF-{order.order_no}-{uuid4().hex[:8].upper()}",
        idempotency_key=payload.get("idempotency_key"),
        metadata={"target_product_operation_id": target_id, "notes": payload.get("notes")}, user_id=user_id,
    )
    if target_id:
        for assignment in db.query(WorkAssignment).filter_by(production_order_id=order.id, product_operation_id=target_id).all():
            if assignment.status == "queued":
                assignment.status = "in_progress"
    else:
        data = dict(order.custom_data or {})
        data["revista_quantity"] = round(float(data.get("revista_quantity") or 0) + quantity, 2)
        order.custom_data = data
    if payload.get("batch_id"):
        batch = db.get(ProductionBatch, int(payload["batch_id"]))
        if batch and batch.production_order_id == order.id:
            batch.current_location = "Revista" if not target_id else f"Operação {target_id}"
    db.flush()
    return {"movement": model_to_dict(movement), "flow": operation_flow(db, order)}


def split_batch(db: Session, batch: ProductionBatch, children: list[dict], user_id: int | None = None) -> list[ProductionBatch]:
    if batch.status in {"merged", "split", "cancelled"}:
        raise ValueError("Este lote já não pode ser dividido")
    quantities = [round(float(item.get("quantity") or 0), 2) for item in children]
    if not quantities or any(value <= EPSILON for value in quantities):
        raise ValueError("Indique quantidades válidas para os novos lotes")
    if abs(sum(quantities) - float(batch.quantity or 0)) > EPSILON:
        raise ValueError("A soma dos novos lotes tem de ser igual à quantidade do lote original")
    created = []
    for index, (item, quantity) in enumerate(zip(children, quantities), start=1):
        child = ProductionBatch(
            company_id=batch.company_id, production_order_id=batch.production_order_id,
            sewing_line_id=batch.sewing_line_id, variant_id=item.get("variant_id") or batch.variant_id,
            source_cutting_job_id=batch.source_cutting_job_id,
            batch_no=str(item.get("batch_no") or f"{batch.batch_no}-{index:02d}"),
            color=item.get("color") or batch.color, size=item.get("size") or batch.size,
            quantity=quantity, completed_quantity=0, current_operation_id=batch.current_operation_id,
            current_location=batch.current_location, status="waiting", kanban_status="waiting",
            barcode=item.get("barcode"),
        )
        db.add(child)
        db.flush()
        db.add(BatchGenealogy(
            company_id=batch.company_id, parent_batch_id=batch.id, child_batch_id=child.id,
            relation_type="split", quantity=quantity, user_id=user_id, notes=item.get("notes"),
        ))
        record_movement(
            db, company_id=batch.company_id, production_order_id=batch.production_order_id,
            batch_id=child.id, variant_id=child.variant_id, movement_type="batch_split", quantity=quantity,
            location_from=f"batch:{batch.id}", location_to=f"batch:{child.id}",
            reference=child.batch_no, idempotency_key=f"batch-split:{batch.id}:{child.id}", user_id=user_id,
        )
        created.append(child)
    batch.status = "split"
    batch.kanban_status = "split"
    db.flush()
    return created


def merge_batches(db: Session, parents: list[ProductionBatch], payload: dict, user_id: int | None = None) -> ProductionBatch:
    if len(parents) < 2:
        raise ValueError("Escolha pelo menos dois lotes")
    order_ids = {row.production_order_id for row in parents}
    if len(order_ids) != 1 or any(row.status in {"merged", "split", "cancelled"} for row in parents):
        raise ValueError("Os lotes têm de estar ativos e pertencer à mesma OF")
    total = round(sum(float(row.quantity or 0) for row in parents), 2)
    first = parents[0]
    child = ProductionBatch(
        company_id=first.company_id, production_order_id=first.production_order_id,
        sewing_line_id=first.sewing_line_id, variant_id=payload.get("variant_id") or first.variant_id,
        batch_no=str(payload.get("batch_no") or "").strip(), color=payload.get("color") or first.color,
        size=payload.get("size") or first.size, quantity=total, completed_quantity=0,
        current_operation_id=first.current_operation_id, current_location=first.current_location,
        status="waiting", kanban_status="waiting", barcode=payload.get("barcode"),
    )
    if not child.batch_no:
        raise ValueError("Indique o número do novo lote")
    db.add(child)
    db.flush()
    for parent in parents:
        parent.status = "merged"
        parent.kanban_status = "merged"
        db.add(BatchGenealogy(
            company_id=parent.company_id, parent_batch_id=parent.id, child_batch_id=child.id,
            relation_type="merge", quantity=parent.quantity, user_id=user_id,
        ))
        record_movement(
            db, company_id=parent.company_id, production_order_id=parent.production_order_id,
            batch_id=child.id, variant_id=child.variant_id, movement_type="batch_merge",
            quantity=parent.quantity, location_from=f"batch:{parent.id}", location_to=f"batch:{child.id}",
            reference=child.batch_no, idempotency_key=f"batch-merge:{parent.id}:{child.id}", user_id=user_id,
        )
    db.flush()
    return child


def batch_trace(db: Session, batch: ProductionBatch) -> dict:
    all_edges = db.query(BatchGenealogy).filter_by(company_id=batch.company_id).all()
    related_ids = {batch.id}
    changed = True
    while changed:
        changed = False
        for edge in all_edges:
            if edge.parent_batch_id in related_ids or edge.child_batch_id in related_ids:
                before = len(related_ids)
                related_ids.update({edge.parent_batch_id, edge.child_batch_id})
                changed = changed or len(related_ids) != before
    edges = [edge for edge in all_edges if edge.parent_batch_id in related_ids and edge.child_batch_id in related_ids]
    batches = db.query(ProductionBatch).filter(ProductionBatch.id.in_(related_ids)).all()
    variants = {row.id: row for row in db.query(StyleVariant).filter(StyleVariant.id.in_([b.variant_id for b in batches if b.variant_id])).all()}
    return {
        "batch": model_to_dict(batch),
        "batches": [{**model_to_dict(row), "variant": model_to_dict(variants[row.variant_id]) if row.variant_id in variants else None} for row in batches],
        "edges": [model_to_dict(row) for row in edges],
        "movements": [model_to_dict(row) for row in db.query(ProductionMovement).filter(ProductionMovement.batch_id.in_(related_ids)).order_by(ProductionMovement.id).all()],
    }


def sync_quality_movement(db: Session, inspection: QualityInspection, user_id: int | None = None) -> list[ProductionMovement]:
    if not inspection.production_order_id or inspection.result == "pending":
        return []
    batch = db.get(ProductionBatch, inspection.batch_id) if inspection.batch_id else None
    variant_id = inspection.variant_id or (batch.variant_id if batch else None)
    inspected = max(0.0, float(inspection.inspected_quantity or 0))
    defects = min(inspected, max(0.0, float(inspection.defect_quantity or 0)))
    good = max(0.0, inspected - defects)
    rows = []
    if inspection.inspection_type not in {"final", "revista"}:
        return [record_movement(
            db, company_id=inspection.company_id, production_order_id=inspection.production_order_id,
            batch_id=inspection.batch_id, variant_id=variant_id, quality_inspection_id=inspection.id,
            movement_type="quality_checkpoint", quantity=inspected, location_from="production", location_to="production",
            reference=f"Inspeção #{inspection.id}", idempotency_key=f"quality:{inspection.id}:checkpoint:{inspection.result}",
            metadata={"result": inspection.result, "defect_quantity": defects}, user_id=user_id,
        )]
    if inspection.result == "passed":
        inspection.disposition = "released"
        inspection.released_quantity = good
        target_rows = [("quality_release", good, "quality_approved")]
    elif inspection.result == "conditional":
        inspection.disposition = "rework" if defects else "released"
        inspection.released_quantity = good
        inspection.rework_quantity = defects
        # O material fica primeiro em quarentena; a ordem de retrabalho é que o
        # transfere depois para a área de retrabalho, mantendo um único percurso.
        target_rows = [("quality_release", good, "quality_approved"), ("quality_hold", defects, "quarantine")]
    else:
        inspection.disposition = "quarantine"
        inspection.rework_quantity = inspected
        target_rows = [("quality_hold", inspected, "quarantine")]
    for movement_type, quantity, target in target_rows:
        if quantity <= EPSILON:
            continue
        rows.append(record_movement(
            db, company_id=inspection.company_id, production_order_id=inspection.production_order_id,
            batch_id=inspection.batch_id, variant_id=variant_id,
            quality_inspection_id=inspection.id, movement_type=movement_type, quantity=quantity,
            location_from="quality_inspection", location_to=target,
            reference=f"Inspeção #{inspection.id}",
            idempotency_key=f"quality:{inspection.id}:{movement_type}:{inspection.result}", user_id=user_id,
        ))
    db.flush()
    return rows


def sync_subcontract_receipt(db: Session, job, previous_accepted: float = 0, previous_rejected: float = 0, user_id: int | None = None) -> list[ProductionMovement]:
    """Regista apenas o incremento recebido; o histórico anterior nunca é reescrito."""
    if not job.production_order_id:
        return []
    accepted_delta = round(float(job.accepted_quantity or 0) - float(previous_accepted or 0), 2)
    rejected_delta = round(float(job.rejected_quantity or 0) - float(previous_rejected or 0), 2)
    if accepted_delta < -EPSILON or rejected_delta < -EPSILON:
        raise ValueError("Quantidades já recebidas de um subcontrato não podem ser reduzidas")
    rows = []
    for kind, quantity, target in (("subcontract_receipt", accepted_delta, "received_external"), ("subcontract_reject", rejected_delta, "quarantine")):
        if quantity <= EPSILON:
            continue
        rows.append(record_movement(
            db, company_id=job.company_id, production_order_id=job.production_order_id,
            movement_type=kind, quantity=quantity, location_from=f"subcontract:{job.supplier_id}", location_to=target,
            reference=job.reference, idempotency_key=f"subcontract:{job.id}:{kind}:{float(getattr(job, 'accepted_quantity' if kind == 'subcontract_receipt' else 'rejected_quantity') or 0):g}",
            metadata={"subcontract_job_id": job.id, "service_id": job.subcontract_service_id}, user_id=user_id,
        ))
    return rows
