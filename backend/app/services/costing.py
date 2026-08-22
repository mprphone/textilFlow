from sqlalchemy import func

from ..models import BOMItem, CostLine, CostSheet, Material, Operation, ProductOperation


def rebuild_product_cost(db, sheet: CostSheet) -> CostSheet:
    db.query(CostLine).filter(
        CostLine.cost_sheet_id == sheet.id,
        CostLine.source_type.in_(["bom", "operation", "wizard_material", "wizard_accessory", "wizard_operation"]),
    ).delete(synchronize_session=False)

    bom_rows = db.query(BOMItem, Material).join(Material, Material.id == BOMItem.material_id).filter(
        BOMItem.style_id == sheet.style_id
    ).all()
    for bom, material in bom_rows:
        unit_cost = bom.unit_cost or material.unit_cost or 0
        quantity = (bom.quantity or 0) * (1 + (bom.waste_pct or 0) / 100)
        db.add(CostLine(
            company_id=sheet.company_id, cost_sheet_id=sheet.id, category="material",
            description=material.name, quantity=quantity, unit=bom.unit,
            unit_cost=unit_cost, amount=quantity * unit_cost, source_type="bom", source_id=bom.id,
        ))

    operation_rows = db.query(ProductOperation, Operation).join(
        Operation, Operation.id == ProductOperation.operation_id
    ).filter(ProductOperation.style_id == sheet.style_id).all()
    for product_operation, operation in operation_rows:
        minutes = product_operation.smv or operation.standard_time_min or 0
        rate = operation.cost_per_minute or 0
        db.add(CostLine(
            company_id=sheet.company_id, cost_sheet_id=sheet.id, category="labor",
            description=operation.name, quantity=minutes, unit="min",
            unit_cost=rate, amount=minutes * rate, source_type="operation", source_id=product_operation.id,
        ))
    db.flush()
    return recalculate_sheet(db, sheet)


def recalculate_sheet(db, sheet: CostSheet) -> CostSheet:
    lines = db.query(CostLine).filter(CostLine.cost_sheet_id == sheet.id).all()
    totals = {key: 0.0 for key in ("material", "labor", "machine", "subcontract", "overhead", "other")}
    for line in lines:
        line.amount = round((line.quantity or 0) * (line.unit_cost or 0), 4)
        totals[line.category if line.category in totals else "other"] += line.amount
    sheet.material_cost = totals["material"]
    sheet.labor_cost = totals["labor"]
    sheet.machine_cost = totals["machine"]
    sheet.subcontract_cost = totals["subcontract"]
    sheet.overhead_cost = totals["overhead"]
    sheet.other_cost = totals["other"]
    sheet.total_cost = round(sum(totals.values()), 4)
    sheet.margin_pct = round(
        ((sheet.selling_price - sheet.total_cost) / sheet.selling_price * 100), 2
    ) if sheet.selling_price else 0
    db.flush()
    return sheet


def refresh_style_costs(db, style_id: int) -> None:
    sheets = db.query(CostSheet).filter(
        CostSheet.style_id == style_id,
        CostSheet.status == "draft",
    ).all()
    for sheet in sheets:
        rebuild_product_cost(db, sheet)
