from datetime import datetime

from sqlalchemy import func

from ..models import (
    ArticleType, BOMItem, CostLine, CostSheet, Customer, Material, Operation,
    ProductOperation, StockLot, Style, SubcontractService, Supplier,
)
from .costing import recalculate_sheet
from .serialization import model_to_dict


def wizard_catalog(db, company_id: int) -> dict:
    suppliers = {row.id: row for row in db.query(Supplier).filter_by(company_id=company_id).all()}
    lots = db.query(StockLot).filter_by(company_id=company_id).all()
    stock = {}
    for lot in lots:
        stock[lot.material_id] = stock.get(lot.material_id, 0) + max(0, (lot.quantity or 0) - (lot.reserved or 0))
    materials = []
    for row in db.query(Material).filter_by(company_id=company_id, active=True).order_by(Material.category, Material.name).all():
        supplier = suppliers.get(row.supplier_id)
        materials.append({
            **model_to_dict(row),
            "available_stock": round(stock.get(row.id, 0), 4),
            "supplier_name": supplier.name if supplier else "Sem fornecedor",
            "image_url": (row.custom_data or {}).get("image_url"),
        })
    subcontract_services = []
    for row in db.query(SubcontractService).filter_by(company_id=company_id, active=True).order_by(SubcontractService.category, SubcontractService.name).all():
        supplier = suppliers.get(row.supplier_id)
        subcontract_services.append({
            **model_to_dict(row),
            "supplier_name": supplier.name if supplier else "Fornecedor desconhecido",
            "supplier_score": supplier.score if supplier else 0,
        })
    return {
        "article_types": [model_to_dict(row) for row in db.query(ArticleType).filter_by(company_id=company_id, active=True).order_by(ArticleType.name).all()],
        "customers": [model_to_dict(row) for row in db.query(Customer).filter_by(company_id=company_id, active=True).order_by(Customer.name).all()],
        "materials": materials,
        "operations": [model_to_dict(row) for row in db.query(Operation).filter_by(company_id=company_id, active=True).order_by(Operation.department, Operation.name).all()],
        "suppliers": [model_to_dict(row) for row in suppliers.values()],
        "subcontract_services": subcontract_services,
    }


def _unique_reference(db, company_id: int, requested: str | None, type_code: str) -> str:
    base = (requested or f"{type_code}-{datetime.now().year}").strip().upper()
    if not db.query(Style).filter_by(company_id=company_id, reference=base).first():
        return base
    index = 2
    while db.query(Style).filter_by(company_id=company_id, reference=f"{base}-{index}").first():
        index += 1
    return f"{base}-{index}"


def create_from_wizard(db, payload) -> tuple[Style, CostSheet]:
    article_type = db.get(ArticleType, payload.article_type_id)
    if not article_type or article_type.company_id != payload.company_id:
        raise ValueError("Tipo de peça inválido")
    material_models = [db.get(Material, item.material_id) for item in [*payload.materials, *payload.accessories] if item.material_id]
    material_models = [row for row in material_models if row and row.company_id == payload.company_id]
    main_fabric = next((row for row in material_models if row.category == "fabric"), None)
    style = Style(
        company_id=payload.company_id,
        article_type_id=article_type.id,
        customer_id=payload.customer_id,
        reference=_unique_reference(db, payload.company_id, payload.reference, article_type.code),
        description=payload.description.strip(),
        lifecycle_status="development",
        workflow_stage="concept",
        image_url=payload.piece_image_url,
        fabric=main_fabric.name if main_fabric else None,
        composition=main_fabric.composition if main_fabric else None,
        gsm=main_fabric.gsm if main_fabric else None,
        color=payload.color,
        custom_data={"created_by": "proposal_wizard", "visuals": {"piece": payload.piece_image_url}},
    )
    db.add(style)
    db.flush()

    for item in [*payload.materials, *payload.accessories]:
        if not item.material_id:
            continue
        material = db.get(Material, item.material_id)
        if not material or material.company_id != payload.company_id:
            continue
        db.add(BOMItem(
            company_id=payload.company_id, style_id=style.id, material_id=material.id,
            quantity=item.quantity, unit=item.unit, waste_pct=item.waste_pct,
            unit_cost=item.unit_cost, notes=f"Selecionado no assistente de proposta · {item.color or ''}".strip(),
        ))

    sequence = 10
    for item in payload.operations:
        if not item.operation_id:
            continue
        operation = db.get(Operation, item.operation_id)
        if not operation or operation.company_id != payload.company_id:
            continue
        db.add(ProductOperation(
            company_id=payload.company_id, style_id=style.id, operation_id=operation.id,
            sequence=sequence, smv=item.quantity, target_units_hour=round(60 / item.quantity, 2) if item.quantity else 0,
        ))
        sequence += 10

    version = (db.query(func.max(CostSheet.version)).filter_by(style_id=style.id).scalar() or 0) + 1
    sheet = CostSheet(
        company_id=payload.company_id, style_id=style.id, version=version, status="draft",
        quantity_basis=payload.quantity, selling_price=payload.selling_price,
        custom_data={
            "customer_id": payload.customer_id,
            "quote_no": None,
            "valid_until": payload.valid_until.isoformat() if payload.valid_until else None,
            "notes": payload.notes,
            "vat_pct": 23,
            "payment_terms": "30 dias",
            "cost_source": "interactive_wizard",
            "visuals": {
                "piece": payload.piece_image_url, "color": payload.color,
                "materials": [item.model_dump(mode="json") for item in payload.materials],
                "accessories": [item.model_dump(mode="json") for item in payload.accessories],
            },
        },
    )
    db.add(sheet)
    db.flush()
    meta = dict(sheet.custom_data)
    meta["quote_no"] = f"PROP-{datetime.now().year}-{sheet.id:05d}"
    sheet.custom_data = meta

    def add_lines(items, category, source_type):
        for item in items:
            if item.subcontract_service_id:
                service = db.get(SubcontractService, item.subcontract_service_id)
                if not service or service.company_id != payload.company_id or not service.active:
                    raise ValueError("O serviço subcontratado já não está disponível")
            quantity = item.quantity * (1 + item.waste_pct / 100)
            db.add(CostLine(
                company_id=payload.company_id, cost_sheet_id=sheet.id, category=category,
                description=item.description.strip(), quantity=round(quantity, 6), unit=item.unit,
                unit_cost=item.unit_cost, amount=round(quantity * item.unit_cost, 4),
                source_type=source_type,
                source_id=item.material_id or item.operation_id or item.subcontract_service_id,
            ))

    add_lines(payload.materials, "material", "wizard_material")
    add_lines(payload.accessories, "material", "wizard_accessory")
    add_lines(payload.operations, "labor", "wizard_operation")
    add_lines(payload.services, "subcontract", "subcontract_service")
    add_lines(payload.overheads, "overhead", "wizard_overhead")
    db.flush()
    recalculate_sheet(db, sheet)
    return style, sheet
