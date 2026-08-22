from ..models import AuditLog


def record_audit(db, *, company_id: int, user_id: int, entity: str, entity_id, action: str, payload=None):
    db.add(AuditLog(
        company_id=company_id,
        user_id=user_id,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        action=action,
        payload=payload or {},
    ))
