from __future__ import annotations

from fastapi import HTTPException

from ..models import ProductionEvent, WorkAssignment
from .production import register_output


class _CompensationPayload:
    """Espelha a interface que register_output espera de um payload, com os
    valores do evento original invertidos - reverte exatamente o que esse
    evento tinha aplicado (quantidades, minutos e por extensao os custos)."""

    def __init__(self, original: ProductionEvent, reason: str):
        self.quantity_good = -(original.quantity_good or 0)
        self.quantity_rejected = -(original.quantity_rejected or 0)
        self.duration_minutes = -(original.duration_minutes or 0)
        self.event_type = "correction"
        self.notes = f"Estorno do evento #{original.id}: {reason}".strip()
        self.source = "correction"
        self.allow_overage = True


def compensate_event(db, event_id: int, reason: str) -> ProductionEvent:
    """Cria um evento de producao inverso ao original, em vez de o editar -
    preserva a imutabilidade dos registos (auditoria, eventos, movimentos).
    """
    original = db.get(ProductionEvent, event_id)
    if not original:
        raise HTTPException(404, "Evento de produção não encontrado")
    if original.event_type == "correction":
        raise HTTPException(422, "Não é possível estornar um estorno; registe um novo evento correto.")
    if not (reason or "").strip():
        raise HTTPException(422, "Indique o motivo do estorno")
    if not original.assignment_id:
        # Evento sem atribuicao associada (caso residual): nao ha efeitos
        # colaterais de assignment/OF a reverter, so o proprio registo.
        compensating = ProductionEvent(
            company_id=original.company_id, production_order_id=original.production_order_id,
            batch_id=original.batch_id, operation_id=original.operation_id,
            employee_id=original.employee_id, machine_id=original.machine_id, line_id=original.line_id,
            event_type="correction", duration_minutes=-(original.duration_minutes or 0),
            quantity_good=-(original.quantity_good or 0), quantity_rejected=-(original.quantity_rejected or 0),
            labor_cost=-(original.labor_cost or 0), machine_cost=-(original.machine_cost or 0),
            notes=f"Estorno do evento #{original.id}: {reason}", source="correction",
        )
        db.add(compensating)
        db.flush()
        return compensating
    assignment = db.get(WorkAssignment, original.assignment_id)
    if not assignment:
        raise HTTPException(404, "Atribuição do evento original não encontrada")
    return register_output(db, assignment, _CompensationPayload(original, reason))
