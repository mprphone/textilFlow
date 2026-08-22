from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from ...models import (
    Certification, CostSheet, CuttingJob, Material, Operation, OverheadCost, ProductOperation,
    ProductionBatch, ProductionOrder, PurchaseOrder, PurchaseOrderLine, QualityInspection,
    SalesOrder, SalesOrderLine, Shipment, StockLot, WorkAssignment,
)
from ..production import register_output


def ensure_demo_followup(db) -> None:
    order = db.query(ProductionOrder).filter_by(order_no="OF-2026-0841").first()
    if not order:
        return
    data = dict(order.custom_data or {})
    if not data.get("approved_cost_sheet_id"):
        sheet = db.query(CostSheet).filter_by(company_id=order.company_id, style_id=order.style_id).order_by(CostSheet.version.desc()).first()
        if sheet:
            data["approved_cost_sheet_id"] = sheet.id
    data.setdefault("commercial_name", "Ana Costa")
    order.custom_data = data
    if order.sales_order_line_id:
        line = db.get(SalesOrderLine, order.sales_order_line_id)
        sales = db.get(SalesOrder, line.sales_order_id) if line else None
        if sales:
            sales_data = dict(sales.custom_data or {})
            sales_data.setdefault("commercial_name", "Ana Costa")
            sales.custom_data = sales_data
    materials = {row.code: row for row in db.query(Material).filter_by(company_id=order.company_id).all()}
    for code, lot_no, quantity, location in (("ETIQ-COMP", "ET-2201", 18000, "B2"), ("SACO-REC", "SC-1188", 8000, "B3")):
        material = materials.get(code)
        if not material or db.query(StockLot).filter_by(company_id=order.company_id, lot_no=lot_no).first():
            continue
        db.add(StockLot(
            company_id=order.company_id, material_id=material.id, lot_no=lot_no, location=location,
            quantity=quantity, reserved=0, unit_cost=material.unit_cost, received_date=date.today() - timedelta(days=12),
        ))


def seed_production(db, foundation: dict, product: dict) -> dict:
    company = foundation["company"]
    sales_order = SalesOrder(
        company_id=company.id, customer_id=foundation["customers"]["ZARA"].id,
        order_no="EC-2026-0841", customer_po="PO-45001981", order_date=date.today() - timedelta(days=20),
        delivery_date=date.today() + timedelta(days=12), status="confirmed",
        custom_data={"commercial_name": "Ana Costa"},
    )
    db.add(sales_order)
    db.flush()
    sales_line = SalesOrderLine(company_id=company.id, sales_order_id=sales_order.id, style_id=product["style"].id, description=product["style"].description, quantity=25000, unit_price=12.20, delivery_date=sales_order.delivery_date)
    db.add(sales_line)
    db.flush()
    production_order = ProductionOrder(
        company_id=company.id, sales_order_line_id=sales_line.id, style_id=product["style"].id,
        line_id=foundation["lines"]["L1"].id, order_no="OF-2026-0841", quantity=25000,
        planned_start=date.today() - timedelta(days=5), planned_end=date.today() + timedelta(days=8),
        status="in_progress", priority=1, current_stage="confeção", current_location="Linha Confeção 1",
        custom_data={"approved_cost_sheet_id": product["sheet"].id, "commercial_name": "Ana Costa"},
    )
    db.add(production_order)
    db.flush()
    batch = ProductionBatch(company_id=company.id, production_order_id=production_order.id, batch_no="LOT-28472-RED-M", color="Vermelho", size="M", quantity=1000, current_location="Linha Confeção 1", status="in_progress", barcode="LOT28472REDM")
    db.add(batch)
    db.flush()

    employee_cycle = ["E003", "E004", "E004", "E003", "E005", "E007"]
    machine_cycle = ["PP-01", "COS-01", "COS-01", "COS-01", "REC-01", None]
    outputs = [820, 780, 760, 690, 650, 610]
    assignments = []
    product_operations = db.query(ProductOperation).filter_by(style_id=product["style"].id).order_by(ProductOperation.sequence).all()
    for index, product_operation in enumerate(product_operations):
        operation = db.get(Operation, product_operation.operation_id)
        employee = foundation["employees"][employee_cycle[index]]
        machine = foundation["machines"].get(machine_cycle[index])
        assignment = WorkAssignment(
            company_id=company.id, production_order_id=production_order.id, batch_id=batch.id,
            product_operation_id=product_operation.id, operation_id=operation.id,
            employee_id=employee.id, machine_id=machine.id if machine else None,
            line_id=foundation["lines"]["L1"].id, planned_quantity=1000,
            standard_minutes=product_operation.smv * 1000, status="in_progress",
        )
        db.add(assignment)
        db.flush()
        assignments.append(assignment)
        register_output(db, assignment, SimpleNamespace(
            quantity_good=outputs[index], quantity_rejected=5 + index,
            duration_minutes=max(240, outputs[index] * product_operation.smv / 0.84),
            event_type="output", notes="Registo inicial demonstrativo", source="terminal",
        ))

    cutting = CuttingJob(
        company_id=company.id, production_order_id=production_order.id, batch_id=batch.id,
        cutter_employee_id=foundation["employees"]["E001"].id, machine_id=foundation["machines"]["CUT-AUTO"].id,
        marker_code="MK-28472-V6", fabric_lot="FL-8821", layers=50, planned_pieces=1000,
        good_pieces=995, rejected_pieces=5, planned_fabric=545, actual_fabric=558,
        waste_pct=10.8, duration_minutes=150, labor_cost=23, machine_cost=60,
        status="completed", started_at=datetime.now(timezone.utc) - timedelta(days=3, hours=3),
        ended_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    db.add(cutting)
    db.add(QualityInspection(
        company_id=company.id, production_order_id=production_order.id, batch_id=batch.id,
        operation_id=product["operations"]["OP60"].id, employee_id=foundation["employees"]["E007"].id,
        inspection_type="inline", inspected_quantity=300, defect_quantity=8,
        defect_code="COSTURA_GOLA", severity="major", result="conditional",
        notes="Regular tensão na operação de gola",
    ))
    db.add(Certification(
        company_id=company.id, supplier_id=foundation["suppliers"]["CONF-S"].id,
        cert_type="GOTS", certificate_no="GOTS-PT-8821",
        issued_date=date.today() - timedelta(days=340), expiry_date=date.today() + timedelta(days=21),
    ))
    for material_code, lot_no, quantity, reserved, location in [
        ("FL320-RED", "FL-8821", 6400, 5100, "A1"),
        ("RIB280-RED", "RB-1094", 920, 700, "A2"),
        ("LINHA-PES", "LP-4402", 40000, 12000, "B1"),
    ]:
        material = product["materials"][material_code]
        db.add(StockLot(company_id=company.id, material_id=material.id, supplier_id=material.supplier_id, lot_no=lot_no, location=location, quantity=quantity, reserved=reserved, unit_cost=material.unit_cost, received_date=date.today() - timedelta(days=30)))
    for material_code, lot_no, quantity, location in [("ETIQ-COMP", "ET-2201", 18000, "B2"), ("SACO-REC", "SC-1188", 8000, "B3")]:
        material = product["materials"][material_code]
        db.add(StockLot(company_id=company.id, material_id=material.id, lot_no=lot_no, location=location, quantity=quantity, reserved=0, unit_cost=material.unit_cost, received_date=date.today() - timedelta(days=12)))
    for category, description, amount, department in [
        ("energy", "Eletricidade fábrica", 4200, "CONF"), ("rent", "Instalações", 6500, None),
        ("maintenance", "Manutenção preventiva", 1800, "COR"), ("administration", "Custos administrativos", 5200, None),
    ]:
        db.add(OverheadCost(company_id=company.id, department_id=foundation["departments"][department].id if department else None, category=category, description=description, period_start=date.today().replace(day=1), period_end=date.today(), amount=amount, allocation_basis="production_minutes"))
    purchase = PurchaseOrder(company_id=company.id, supplier_id=foundation["suppliers"]["MALHA-P"].id, order_no="OC-2026-0142", order_date=date.today(), expected_date=date.today() + timedelta(days=10), status="sent", total=8400)
    db.add(purchase)
    db.flush()
    db.add(PurchaseOrderLine(company_id=company.id, purchase_order_id=purchase.id, material_id=product["materials"]["FL320-RED"].id, quantity=2000, unit_cost=4.20))
    db.add(Shipment(company_id=company.id, sales_order_id=sales_order.id, shipment_no="EXP-2026-0088", carrier="Transportes Demo", destination="Centro Logístico Cliente", quantity=0, status="planned"))
    return {"sales_order": sales_order, "production_order": production_order, "batch": batch, "assignments": assignments}
