from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import (
    BOMItem, CostLine, CostSheet, Material, Operation, ProductOperation, Sample,
    Style, StyleRevision, StyleVariant, User,
)
from ...services.costing import rebuild_product_cost
from ...services.serialization import model_to_dict
from ..deps import current_user, require_module_access


router = APIRouter(prefix="/products", tags=["Produto e PLM"])


@router.get("/styles/{style_id}/full")
def full_style(style_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    style = db.get(Style, style_id)
    if not style:
        raise HTTPException(404, "Artigo não encontrado")
    require_module_access(db, user, style.company_id, {"design", "commercial"})
    bom = db.query(BOMItem, Material).join(Material, Material.id == BOMItem.material_id).filter(BOMItem.style_id == style_id).all()
    routing = db.query(ProductOperation, Operation).join(Operation, Operation.id == ProductOperation.operation_id).filter(ProductOperation.style_id == style_id).order_by(ProductOperation.sequence).all()
    sheets = db.query(CostSheet).filter_by(style_id=style_id).order_by(CostSheet.version.desc()).all()
    return {
        "style": model_to_dict(style),
        "variants": [model_to_dict(row) for row in db.query(StyleVariant).filter_by(style_id=style_id).all()],
        "bom": [{**model_to_dict(item), "material_code": material.code, "material_name": material.name} for item, material in bom],
        "routing": [{**model_to_dict(item), "operation_code": operation.code, "operation_name": operation.name, "machine_type": operation.machine_type} for item, operation in routing],
        "samples": [model_to_dict(row) for row in db.query(Sample).filter_by(style_id=style_id).order_by(Sample.created_at.desc()).all()],
        "cost_sheets": [model_to_dict(row) for row in sheets],
        "revisions": [model_to_dict(row) for row in db.query(StyleRevision).filter_by(style_id=style_id).order_by(StyleRevision.version.desc()).all()],
    }


@router.post("/cost-sheets/{sheet_id}/rebuild")
def rebuild_cost(sheet_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sheet = db.get(CostSheet, sheet_id)
    if not sheet:
        raise HTTPException(404, "Folha de custo não encontrada")
    require_module_access(db, user, sheet.company_id, {"design", "commercial"})
    if sheet.status in {"approved", "production"}:
        raise HTTPException(409, "A proposta aceite esta congelada. Duplique-a para criar uma revisao.")
    rebuild_product_cost(db, sheet)
    db.commit()
    db.refresh(sheet)
    return {
        "sheet": model_to_dict(sheet),
        "lines": [model_to_dict(row) for row in db.query(CostLine).filter_by(cost_sheet_id=sheet.id).order_by(CostLine.category, CostLine.id).all()],
    }


@router.get("/cost-sheets/{sheet_id}")
def cost_detail(sheet_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sheet = db.get(CostSheet, sheet_id)
    if not sheet:
        raise HTTPException(404, "Folha de custo não encontrada")
    require_module_access(db, user, sheet.company_id, {"design", "commercial"})
    return {"sheet": model_to_dict(sheet), "lines": [model_to_dict(row) for row in db.query(CostLine).filter_by(cost_sheet_id=sheet.id).all()]}
