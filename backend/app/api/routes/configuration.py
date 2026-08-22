from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import FieldDefinition, FormTemplate, User, WorkflowDefinition
from ...services.crud import apply_payload
from ...services.serialization import model_to_dict
from ..deps import current_user, require_module_access, require_role


router = APIRouter(prefix="/configuration", tags=["Configuração adaptativa"])


@router.get("/{company_id}/{entity_type}")
def entity_configuration(company_id: int, entity_type: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_module_access(db, user, company_id, {"management"})
    fields = db.query(FieldDefinition).filter_by(company_id=company_id, entity_type=entity_type, active=True).order_by(FieldDefinition.section, FieldDefinition.display_order).all()
    templates = db.query(FormTemplate).filter_by(company_id=company_id, entity_type=entity_type, active=True).order_by(FormTemplate.version.desc()).all()
    workflows = db.query(WorkflowDefinition).filter_by(company_id=company_id, entity_type=entity_type, active=True).order_by(WorkflowDefinition.version.desc()).all()
    return {"fields": [model_to_dict(row) for row in fields], "templates": [model_to_dict(row) for row in templates], "workflows": [model_to_dict(row) for row in workflows]}


@router.post("/fields/{field_id}/new-version")
def version_field(field_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    current = db.get(FieldDefinition, field_id)
    if not current:
        raise HTTPException(404, "Campo não encontrado")
    require_role(db, user, current.company_id, {"admin", "manager"})
    current.active = False
    data = model_to_dict(current)
    for key in ("id", "created_at", "updated_at"):
        data.pop(key, None)
    data.update(payload)
    data["version"] = current.version + 1
    data["active"] = True
    new_field = apply_payload(FieldDefinition(), data, company_id=current.company_id)
    db.add(new_field)
    db.commit()
    db.refresh(new_field)
    return model_to_dict(new_field)


@router.post("/templates/{template_id}/new-version")
def version_template(template_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    current = db.get(FormTemplate, template_id)
    if not current:
        raise HTTPException(404, "Modelo não encontrado")
    require_role(db, user, current.company_id, {"admin", "manager"})
    current.active = False
    new_template = FormTemplate(
        company_id=current.company_id, entity_type=current.entity_type,
        name=payload.get("name", current.name), version=current.version + 1,
        schema=payload.get("schema", current.schema), active=True,
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return model_to_dict(new_template)
