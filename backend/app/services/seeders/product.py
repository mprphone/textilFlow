from datetime import date, timedelta

from ...models import (
    ArticleType, BOMItem, CostLine, CostSheet, Material, Operation, ProductOperation,
    Sample, Style, StyleVariant,
)
from ..costing import recalculate_sheet


def seed_product(db, context: dict) -> dict:
    company = context["company"]
    types = {}
    for code, name, category in [("TSHIRT", "T-shirt", "top"), ("SWEAT", "Sweatshirt", "top"), ("DRESS", "Vestido", "dress")]:
        article_type = ArticleType(company_id=company.id, code=code, name=name, category=category, template_id=context["template"].id, workflow_id=context["workflow"].id)
        db.add(article_type)
        db.flush()
        types[code] = article_type

    materials = {}
    material_rows = [
        ("FL320-RED", "Fleece 320g Vermelho", "fabric", "kg", 4.20, context["suppliers"]["MALHA-P"].id),
        ("RIB280-RED", "Rib 280g Vermelho", "fabric", "kg", 5.10, context["suppliers"]["MALHA-P"].id),
        ("LINHA-PES", "Linha poliéster", "thread", "m", 0.003, None),
        ("ETIQ-COMP", "Etiqueta composição", "trim", "un", 0.08, None),
        ("SACO-REC", "Saco reciclado", "packaging", "un", 0.12, None),
    ]
    for code, name, category, unit, cost, supplier_id in material_rows:
        material = Material(company_id=company.id, supplier_id=supplier_id, code=code, name=name, category=category, unit=unit, unit_cost=cost, minimum_stock=100)
        db.add(material)
        db.flush()
        materials[code] = material

    style = Style(
        company_id=company.id, article_type_id=types["SWEAT"].id,
        customer_id=context["customers"]["ZARA"].id, reference="28472",
        description="Sweatshirt Oversized", collection="AW27", lifecycle_status="approved",
        workflow_stage="produção", fabric="Fleece", composition="95% Algodão / 5% Elastano",
        gsm=320, color="Vermelho", size_range="XS-XL", approved=True,
        custom_data={"fit": "Oversized", "neck_type": "Redonda com rib", "wash_care": "Lavar a 30º", "certification": "GOTS", "measurement_table": {"M": {"peito": 62, "comprimento": 70}}},
    )
    db.add(style)
    db.flush()
    for size in ["XS", "S", "M", "L", "XL"]:
        db.add(StyleVariant(company_id=company.id, style_id=style.id, sku=f"28472-RED-{size}", color="Vermelho", size=size, barcode=f"28472{size}"))
    for code, quantity, waste in [("FL320-RED", 0.545, 8), ("RIB280-RED", 0.055, 5), ("LINHA-PES", 145, 3), ("ETIQ-COMP", 1, 1), ("SACO-REC", 1, 0)]:
        material = materials[code]
        db.add(BOMItem(company_id=company.id, style_id=style.id, material_id=material.id, quantity=quantity, unit=material.unit, waste_pct=waste, unit_cost=material.unit_cost))

    operations = {}
    operation_rows = [
        ("OP10", "Unir ombros", "Confeção", "lockstitch", 0.42, 0.14),
        ("OP20", "Aplicar mangas", "Confeção", "overlock", 0.58, 0.14),
        ("OP30", "Fechar laterais", "Confeção", "overlock", 0.64, 0.14),
        ("OP40", "Preparar e aplicar gola", "Confeção", "overlock", 0.71, 0.15),
        ("OP50", "Aplicar punhos", "Confeção", "coverstitch", 0.49, 0.15),
        ("OP60", "Inspeção final", "Qualidade", "manual", 0.35, 0.17),
    ]
    sequence = 10
    for code, name, department, machine_type, smv, cost_minute in operation_rows:
        operation = Operation(company_id=company.id, code=code, name=name, department=department, machine_type=machine_type, standard_time_min=smv, cost_per_minute=cost_minute)
        db.add(operation)
        db.flush()
        operations[code] = operation
        db.add(ProductOperation(company_id=company.id, style_id=style.id, operation_id=operation.id, sequence=sequence, smv=smv, target_units_hour=round(60 / smv, 1), quality_checkpoint=code == "OP60"))
        sequence += 10

    sample = Sample(
        company_id=company.id, style_id=style.id, sample_type="PPS", version="V3", status="approved",
        responsible_employee_id=context["employees"]["E006"].id, planned_date=date.today() - timedelta(days=30),
        completed_date=date.today() - timedelta(days=28), labor_minutes=165, labor_cost=31.63,
        material_cost=7.85, external_cost=0, total_cost=39.48, comments="Aprovada para produção",
    )
    db.add(sample)
    sheet = CostSheet(company_id=company.id, style_id=style.id, version=1, status="approved", selling_price=12.20)
    db.add(sheet)
    db.flush()
    for category, description, quantity, unit, unit_cost in [
        ("subcontract", "Tinturaria", 1, "un", 0.60), ("subcontract", "Estampagem", 1, "un", 0.70),
        ("overhead", "Custos gerais fabris", 1, "un", 0.55), ("other", "Transporte", 1, "un", 0.12),
    ]:
        db.add(CostLine(company_id=company.id, cost_sheet_id=sheet.id, category=category, description=description, quantity=quantity, unit=unit, unit_cost=unit_cost, amount=quantity * unit_cost))
    db.flush()
    from ..costing import rebuild_product_cost
    rebuild_product_cost(db, sheet)
    return {"types": types, "materials": materials, "style": style, "operations": operations, "sample": sample, "sheet": sheet}
