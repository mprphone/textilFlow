from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..models import (
    ActualCostEntry, Customer, CustomerClaim, CustomerReturnLine, FinishedGoodsUnit,
    IntegrationReconciliation, Material, ProcurementSuggestion, ProductionBatch,
    ProductionMaterialRequirement, ProductionMovement, ProductionOrder, PurchaseOrder,
    PurchaseOrderLine, QualityInspection, ReworkOrder, SalesOrder, Shipment,
    ShipmentAllocation, ShipmentLine, StyleVariant, Supplier, Warehouse,
)
from .execution import EPSILON, movement_holdings, record_movement
from .serialization import model_to_dict


def _code(prefix: str, identifier: int | str) -> str:
    return f"{prefix}-{identifier}"


def create_finished_goods_unit(db: Session, order: ProductionOrder, payload: dict, user_id: int | None = None) -> FinishedGoodsUnit:
    quantity = round(float(payload.get("quantity") or 0), 2)
    if quantity <= EPSILON:
        raise ValueError("Indique uma quantidade válida")
    variant_id = int(payload.get("variant_id") or 0) or None
    batch_id = int(payload.get("batch_id") or 0) or None
    if batch_id:
        batch = db.get(ProductionBatch, batch_id)
        if not batch or batch.production_order_id != order.id:
            raise ValueError("O lote não pertence a esta OF")
        variant_id = variant_id or batch.variant_id
        if batch.variant_id and variant_id != batch.variant_id:
            raise ValueError("A variante não corresponde ao lote")
    if variant_id:
        variant = db.get(StyleVariant, variant_id)
        if not variant or variant.style_id != order.style_id:
            raise ValueError("A variante não pertence ao artigo da OF")
    warehouse_id = int(payload.get("warehouse_id") or 0) or None
    if warehouse_id:
        warehouse = db.get(Warehouse, warehouse_id)
        if not warehouse or warehouse.company_id != order.company_id:
            raise ValueError("Armazém inválido")
    else:
        warehouse = db.query(Warehouse).filter_by(company_id=order.company_id, active=True).order_by(Warehouse.id).first()
        warehouse_id = warehouse.id if warehouse else None
    next_index = db.query(FinishedGoodsUnit).filter_by(company_id=order.company_id, production_order_id=order.id).count() + 1
    package_code = str(payload.get("package_code") or f"CX-{order.order_no}-{next_index:03d}").strip()
    barcode = str(payload.get("barcode") or f"FG-{order.company_id}-{order.id}-{next_index:04d}").strip()
    if db.query(FinishedGoodsUnit.id).filter_by(company_id=order.company_id, package_code=package_code).first():
        raise ValueError("Já existe uma unidade logística com este código")
    unit = FinishedGoodsUnit(
        company_id=order.company_id, production_order_id=order.id, variant_id=variant_id,
        batch_id=batch_id, warehouse_id=warehouse_id, package_code=package_code,
        package_type=str(payload.get("package_type") or "box"), barcode=barcode,
        initial_quantity=quantity, quantity=quantity, reserved_quantity=0, unit_cost=float(payload.get("unit_cost") or 0),
        status=payload.get("status") or "available", location=payload.get("location") or (warehouse.location if warehouse else "Produto acabado"),
        metadata_json={"boxes": payload.get("boxes"), "notes": payload.get("notes")},
    )
    db.add(unit)
    db.flush()
    movement = record_movement(
        db, company_id=order.company_id, production_order_id=order.id, batch_id=batch_id,
        variant_id=variant_id, finished_goods_unit_id=unit.id,
        customer_return_id=int(payload.get("customer_return_id") or 0) or None,
        movement_type=payload.get("movement_type") or "packing", quantity=quantity,
        location_from=payload.get("location_from") or "revista", location_to=payload.get("location_to") or "finished_goods", reference=package_code,
        idempotency_key=f"finished-goods-pack:{unit.id}", user_id=user_id,
        metadata={"warehouse_id": warehouse_id, "barcode": barcode, "package_type": unit.package_type},
    )
    packaging_cost = round(quantity * float(payload.get("packaging_unit_cost") or 0), 4)
    if packaging_cost > 0:
        db.add(ActualCostEntry(company_id=order.company_id, production_order_id=order.id, category="packaging", description=f"Embalagem {package_code}", quantity=quantity, unit="un", unit_cost=float(payload.get("packaging_unit_cost")), amount=packaging_cost, occurred_on=date.today(), reference=f"packing:{unit.id}"))
    db.flush()
    unit.metadata_json = {**unit.metadata_json, "movement_id": movement.id}
    return unit


def finished_goods_board(db: Session, company_id: int, limit: int = 250) -> dict:
    units = db.query(FinishedGoodsUnit).filter_by(company_id=company_id).filter(FinishedGoodsUnit.status != "cancelled").order_by(FinishedGoodsUnit.packed_at.desc()).limit(max(1, min(limit, 1000))).all()
    rows = []
    for unit in units:
        order = db.get(ProductionOrder, unit.production_order_id)
        variant = db.get(StyleVariant, unit.variant_id) if unit.variant_id else None
        warehouse = db.get(Warehouse, unit.warehouse_id) if unit.warehouse_id else None
        initial = max(float(unit.initial_quantity or 0), float(unit.quantity or 0))
        rows.append({**model_to_dict(unit), "initial_quantity": round(initial, 2), "shipped_quantity": round(max(0.0, initial - float(unit.quantity or 0)), 2), "order_no": order.order_no if order else None, "variant": " · ".join(value for value in ((variant.color if variant else None), (variant.size if variant else None)) if value), "warehouse": warehouse.name if warehouse else None, "available_quantity": round(max(0.0, float(unit.quantity or 0) - float(unit.reserved_quantity or 0)), 2)})
    return {"items": rows, "available_quantity": round(sum(row["available_quantity"] for row in rows if row["status"] == "available"), 2), "quarantine_quantity": round(sum(float(row["quantity"] or 0) for row in rows if row["status"] == "quarantine"), 2)}


def _ensure_legacy_finished_goods(db: Session, order: ProductionOrder) -> None:
    if db.query(FinishedGoodsUnit.id).filter_by(production_order_id=order.id).first():
        return
    stock = movement_holdings(db, order)
    data = order.custom_data or {}
    legacy = max(0.0, float(data.get("packed_quantity") or 0) - float(data.get("shipped_quantity") or 0))
    available = max(stock["finished_goods"], legacy)
    if available <= EPSILON:
        return
    unit = FinishedGoodsUnit(company_id=order.company_id, production_order_id=order.id, package_code=f"LEGACY-{order.order_no}", package_type="legacy", barcode=f"FG-LEGACY-{order.company_id}-{order.id}", initial_quantity=available, quantity=available, status="available", location="Produto acabado", metadata_json={"backfilled": True})
    db.add(unit)
    db.flush()
    if legacy > stock["finished_goods"] + EPSILON:
        record_movement(
            db, company_id=order.company_id, production_order_id=order.id,
            movement_type="distribution", quantity=legacy - stock["finished_goods"],
            location_from="unassigned", location_to="finished_goods",
            reference="Migração de produto acabado",
            idempotency_key=f"legacy-finished-goods:{order.id}",
        )


def allocate_finished_goods(db: Session, shipment: Shipment, line: ShipmentLine, user_id: int | None = None) -> list[ShipmentAllocation]:
    order = db.get(ProductionOrder, line.production_order_id)
    _ensure_legacy_finished_goods(db, order)
    query = db.query(FinishedGoodsUnit).filter_by(company_id=line.company_id, production_order_id=line.production_order_id, status="available")
    if line.variant_id:
        query = query.filter(FinishedGoodsUnit.variant_id == line.variant_id)
    units = query.order_by(FinishedGoodsUnit.packed_at, FinishedGoodsUnit.id).with_for_update().all()
    remaining = float(line.quantity or 0)
    allocations = []
    for unit in units:
        if remaining <= EPSILON:
            break
        available = max(0.0, float(unit.quantity or 0) - float(unit.reserved_quantity or 0))
        take = round(min(available, remaining), 2)
        if take <= EPSILON:
            continue
        allocation = ShipmentAllocation(company_id=line.company_id, shipment_line_id=line.id, finished_goods_unit_id=unit.id, quantity=take)
        db.add(allocation)
        unit.quantity = round(float(unit.quantity or 0) - take, 2)
        unit.status = "shipped" if unit.quantity <= EPSILON else "available"
        record_movement(db, company_id=line.company_id, production_order_id=line.production_order_id, batch_id=unit.batch_id, variant_id=line.variant_id or unit.variant_id, shipment_id=shipment.id, finished_goods_unit_id=unit.id, movement_type="shipment", quantity=take, location_from="finished_goods", location_to="shipped", reference=shipment.shipment_no, idempotency_key=f"shipment-allocation:{line.id}:{unit.id}", user_id=user_id)
        allocations.append(allocation)
        remaining = round(remaining - take, 2)
    if remaining > EPSILON:
        raise ValueError(f"Faltam {remaining:g} unidades físicas em produto acabado para completar a expedição")
    db.flush()
    return allocations


def ensure_rework_for_inspection(db: Session, inspection: QualityInspection, user_id: int | None = None) -> ReworkOrder | None:
    quantity = float(inspection.rework_quantity or 0)
    if quantity <= EPSILON or not inspection.production_order_id or inspection.disposition != "rework":
        return None
    reference = f"RW-Q{inspection.id}"
    existing = db.query(ReworkOrder).filter_by(company_id=inspection.company_id, reference=reference).first()
    if existing:
        return existing
    order = db.get(ProductionOrder, inspection.production_order_id)
    row = ReworkOrder(company_id=inspection.company_id, production_order_id=inspection.production_order_id, quality_inspection_id=inspection.id, batch_id=inspection.batch_id, variant_id=inspection.variant_id, reference=reference, barcode=f"RW-{inspection.company_id}-{inspection.id}", quantity=quantity, status="open", reason=inspection.defect_code or inspection.notes)
    db.add(row)
    db.flush()
    record_movement(db, company_id=row.company_id, production_order_id=row.production_order_id, batch_id=row.batch_id, variant_id=row.variant_id, quality_inspection_id=inspection.id, rework_order_id=row.id, movement_type="rework_start", quantity=quantity, location_from="quarantine", location_to="rework", reference=reference, idempotency_key=f"rework-start:{row.id}", user_id=user_id)
    return row


def dispose_quality_hold(db: Session, inspection: QualityInspection, disposition: str, user_id: int | None = None) -> dict:
    if inspection.result != "failed" or inspection.disposition != "quarantine":
        raise ValueError("Esta inspeção já não está pendente de destino")
    if disposition not in {"rework", "scrap", "reinspect"}:
        raise ValueError("Destino de qualidade inválido")
    quantity = float(inspection.inspected_quantity or 0)
    if disposition == "rework":
        inspection.disposition = "rework"
        inspection.rework_quantity = quantity
        rework = ensure_rework_for_inspection(db, inspection, user_id)
        result = {"rework_order_id": rework.id if rework else None}
    elif disposition == "scrap":
        inspection.disposition = "scrap"
        inspection.scrap_quantity = quantity
        movement = record_movement(
            db, company_id=inspection.company_id, production_order_id=inspection.production_order_id,
            batch_id=inspection.batch_id, variant_id=inspection.variant_id,
            quality_inspection_id=inspection.id, movement_type="scrap", quantity=quantity,
            location_from="quarantine", location_to="scrap", reference=f"Q-{inspection.id}",
            idempotency_key=f"quality-scrap:{inspection.id}", user_id=user_id,
        )
        result = {"movement_id": movement.id}
    else:
        inspection.disposition = "reinspection"
        retry = QualityInspection(
            company_id=inspection.company_id, production_order_id=inspection.production_order_id,
            batch_id=inspection.batch_id, variant_id=inspection.variant_id,
            inspection_type=inspection.inspection_type, inspected_quantity=quantity,
            result="pending", disposition="pending", notes=f"Reinspeção da inspeção #{inspection.id}",
        )
        db.add(retry)
        db.flush()
        result = {"quality_inspection_id": retry.id}
    db.flush()
    return {"inspection": model_to_dict(inspection), **result}


def complete_rework(db: Session, row: ReworkOrder, payload: dict, user_id: int | None = None) -> dict:
    if row.status in {"completed", "cancelled"}:
        raise ValueError("Esta ordem de retrabalho já está fechada")
    completed = round(float(payload.get("completed_quantity") or 0), 2)
    scrap = round(float(payload.get("scrap_quantity") or 0), 2)
    processed = float(row.completed_quantity or 0) + float(row.scrap_quantity or 0)
    remaining = max(0.0, round(float(row.quantity or 0) - processed, 2))
    if completed < 0 or scrap < 0 or completed + scrap <= EPSILON:
        raise ValueError("Indique peças recuperadas ou desperdício")
    if completed + scrap > remaining + EPSILON:
        raise ValueError(f"Só faltam tratar {remaining:g} unidades deste retrabalho")
    new_completed = round(float(row.completed_quantity or 0) + completed, 2)
    new_scrap = round(float(row.scrap_quantity or 0) + scrap, 2)
    row.completed_quantity = new_completed
    row.scrap_quantity = new_scrap
    row.resolution_notes = payload.get("notes")
    row.status = "completed" if new_completed + new_scrap >= float(row.quantity or 0) - EPSILON else "in_progress"
    if completed > EPSILON:
        record_movement(db, company_id=row.company_id, production_order_id=row.production_order_id, batch_id=row.batch_id, variant_id=row.variant_id, rework_order_id=row.id, movement_type="rework_complete", quantity=completed, location_from="rework", location_to="quality_inspection", reference=row.reference, idempotency_key=f"rework-complete:{row.id}:total:{new_completed:g}", user_id=user_id)
        inspection = QualityInspection(company_id=row.company_id, production_order_id=row.production_order_id, batch_id=row.batch_id, variant_id=row.variant_id, inspection_type="revista", inspected_quantity=completed, result="pending", disposition="pending", notes=f"Reinspeção do retrabalho {row.reference}")
        db.add(inspection)
    if scrap > EPSILON:
        record_movement(db, company_id=row.company_id, production_order_id=row.production_order_id, batch_id=row.batch_id, variant_id=row.variant_id, rework_order_id=row.id, movement_type="scrap", quantity=scrap, location_from="rework", location_to="scrap", reference=row.reference, idempotency_key=f"rework-scrap:{row.id}:total:{new_scrap:g}", user_id=user_id)
    cost = round(float(payload.get("labor_cost") or 0) + float(payload.get("material_cost") or 0) + float(payload.get("energy_cost") or 0), 4)
    if cost > 0:
        db.add(ActualCostEntry(company_id=row.company_id, production_order_id=row.production_order_id, category="rework", description=f"Retrabalho {row.reference}", quantity=completed + scrap, unit="un", unit_cost=cost / max(1, completed + scrap), amount=cost, occurred_on=date.today(), reference=f"rework:{row.id}:{new_completed + new_scrap:g}"))
    db.flush()
    return {"rework": model_to_dict(row)}


def create_customer_claim(db: Session, company_id: int, payload: dict, user_id: int | None = None) -> dict:
    sales = db.get(SalesOrder, int(payload.get("sales_order_id") or 0))
    shipment = db.get(Shipment, int(payload.get("shipment_id") or 0)) if payload.get("shipment_id") else None
    if not sales or sales.company_id != company_id or (shipment and shipment.sales_order_id != sales.id):
        raise ValueError("Encomenda ou expedição inválida")
    claim_no = str(payload.get("claim_no") or f"REC-{sales.order_no}-{db.query(CustomerClaim).filter_by(company_id=company_id).count()+1:03d}")
    claim = CustomerClaim(company_id=company_id, sales_order_id=sales.id, shipment_id=shipment.id if shipment else None, customer_id=sales.customer_id, claim_no=claim_no, claim_type=payload.get("claim_type") or "quality", quantity=float(payload.get("quantity") or 0), severity=payload.get("severity") or "major", reason=payload.get("reason"), status="open")
    db.add(claim)
    db.flush()
    return_lines = []
    for item in payload.get("lines") or []:
        shipment_line = db.get(ShipmentLine, int(item.get("shipment_line_id") or 0))
        allocation = db.get(ShipmentAllocation, int(item.get("shipment_allocation_id") or 0)) if item.get("shipment_allocation_id") else None
        quantity = round(float(item.get("quantity") or 0), 2)
        if not shipment_line or shipment_line.company_id != company_id or (shipment and shipment_line.shipment_id != shipment.id) or quantity <= EPSILON:
            raise ValueError("Linha de devolução inválida")
        if allocation and (allocation.company_id != company_id or allocation.shipment_line_id != shipment_line.id):
            raise ValueError("A caixa/lote não pertence à linha expedida")
        if not allocation:
            allocations = db.query(ShipmentAllocation).filter_by(shipment_line_id=shipment_line.id).all()
            allocation = allocations[0] if len(allocations) == 1 else None
        scope = {"shipment_allocation_id": allocation.id} if allocation else {"shipment_line_id": shipment_line.id}
        limit = float(allocation.quantity if allocation else shipment_line.quantity or 0)
        already = sum(float(returned.quantity or 0) for returned in db.query(CustomerReturnLine).filter_by(**scope).all())
        if already + quantity > limit + EPSILON:
            raise ValueError("A devolução ultrapassa a quantidade expedida nessa linha")
        unit = db.get(FinishedGoodsUnit, allocation.finished_goods_unit_id) if allocation else None
        row = CustomerReturnLine(
            company_id=company_id, customer_claim_id=claim.id, shipment_line_id=shipment_line.id,
            shipment_allocation_id=allocation.id if allocation else None,
            finished_goods_unit_id=unit.id if unit else None,
            production_order_id=shipment_line.production_order_id, variant_id=shipment_line.variant_id or (unit.variant_id if unit else None),
            batch_id=unit.batch_id if unit else None, quantity=quantity,
            disposition=item.get("disposition") or "quarantine", notes=item.get("notes"),
        )
        db.add(row)
        db.flush()
        record_movement(db, company_id=company_id, production_order_id=row.production_order_id, variant_id=row.variant_id, customer_return_id=row.id, movement_type="return_receipt", quantity=quantity, location_from="shipped", location_to="quarantine", reference=claim.claim_no, idempotency_key=f"customer-return:{row.id}", user_id=user_id)
        return_lines.append(row)
    claim.quantity = round(sum(float(row.quantity or 0) for row in return_lines) or float(claim.quantity or 0), 2)
    db.flush()
    return {"claim": model_to_dict(claim), "lines": [model_to_dict(row) for row in return_lines]}


def dispose_customer_return(db: Session, row: CustomerReturnLine, disposition: str, user_id: int | None = None) -> dict:
    if row.status != "received":
        raise ValueError("Esta devolução já teve destino")
    if disposition not in {"restock", "rework", "scrap", "second_quality"}:
        raise ValueError("Destino de devolução inválido")
    row.disposition = disposition
    row.status = "processed"
    if disposition in {"restock", "second_quality"}:
        order = db.get(ProductionOrder, row.production_order_id)
        create_finished_goods_unit(db, order, {
            "quantity": row.quantity, "variant_id": row.variant_id, "batch_id": row.batch_id,
            "package_code": f"DEV-{row.id}", "barcode": f"FG-RETURN-{row.id}",
            "notes": "Reentrada de devolução" if disposition == "restock" else "Devolução classificada como segunda qualidade",
            "location_from": "quarantine",
            "location_to": "finished_goods" if disposition == "restock" else "second_quality",
            "location": "Produto acabado" if disposition == "restock" else "Segunda qualidade",
            "status": "available" if disposition == "restock" else "second_quality",
            "movement_type": "return_disposition", "customer_return_id": row.id,
        }, user_id)
    else:
        target = "rework" if disposition == "rework" else "scrap"
        movement_type = "rework_start" if disposition == "rework" else "scrap"
        record_movement(db, company_id=row.company_id, production_order_id=row.production_order_id, batch_id=row.batch_id, variant_id=row.variant_id, customer_return_id=row.id, movement_type=movement_type, quantity=row.quantity, location_from="quarantine", location_to=target, reference=f"DEV-{row.id}", idempotency_key=f"return-disposition:{row.id}", user_id=user_id)
    if disposition == "rework":
        claim = db.get(CustomerClaim, row.customer_claim_id)
        rework = ReworkOrder(company_id=row.company_id, production_order_id=row.production_order_id, batch_id=row.batch_id, variant_id=row.variant_id, reference=f"RW-DEV-{row.id}", barcode=f"RW-RETURN-{row.id}", quantity=row.quantity, status="open", reason=claim.reason if claim else "Devolução de cliente")
        db.add(rework)
    db.flush()
    return model_to_dict(row)


def refresh_procurement_suggestions(db: Session, company_id: int) -> list[ProcurementSuggestion]:
    active = set()
    requirements = db.query(ProductionMaterialRequirement).filter_by(company_id=company_id).filter(ProductionMaterialRequirement.shortage_quantity > EPSILON).all()
    for req in requirements:
        order = db.get(ProductionOrder, req.production_order_id)
        if not order or order.status in {"completed", "cancelled"} or not req.material_id:
            continue
        material = db.get(Material, req.material_id)
        open_po = sum(max(0.0, float(line.quantity or 0) - float(line.received_quantity or 0)) for line, purchase in db.query(PurchaseOrderLine, PurchaseOrder).join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id).filter(PurchaseOrder.company_id == company_id, PurchaseOrder.status.notin_(["cancelled", "received"]), PurchaseOrderLine.material_id == req.material_id).all())
        suggested = max(0.0, float(req.shortage_quantity or 0) - open_po)
        fingerprint = f"material:{req.material_id}:order:{order.id}"
        active.add(fingerprint)
        row = db.query(ProcurementSuggestion).filter_by(company_id=company_id, fingerprint=fingerprint).first()
        if not row:
            row = ProcurementSuggestion(company_id=company_id, fingerprint=fingerprint, production_order_id=order.id, material_id=req.material_id)
            db.add(row)
        row.supplier_id = material.supplier_id if material else None
        row.required_quantity = req.required_quantity
        row.available_quantity = req.available_quantity
        row.suggested_quantity = round(suggested, 4)
        row.estimated_unit_cost = float(material.unit_cost or 0) if material else 0
        row.needed_by = order.planned_start or order.planned_end
        if row.status not in {"converted", "dismissed"}:
            row.status = "suggested" if suggested > EPSILON else "covered"
        elif row.status == "converted" and suggested > EPSILON:
            purchase = db.get(PurchaseOrder, row.purchase_order_id) if row.purchase_order_id else None
            if not purchase or purchase.status in {"cancelled", "received"}:
                row.purchase_order_id = None
                row.status = "suggested"
    db.flush()
    return db.query(ProcurementSuggestion).filter_by(company_id=company_id).filter(ProcurementSuggestion.status.in_(["suggested", "covered"])).order_by(ProcurementSuggestion.needed_by).all()


def convert_procurement(db: Session, company_id: int, suggestion_ids: list[int]) -> list[PurchaseOrder]:
    suggestions = db.query(ProcurementSuggestion).filter(ProcurementSuggestion.company_id == company_id, ProcurementSuggestion.id.in_(suggestion_ids), ProcurementSuggestion.status == "suggested").all()
    if not suggestions:
        raise ValueError("Não existem sugestões válidas para converter")
    by_supplier = {}
    for row in suggestions:
        if not row.supplier_id:
            raise ValueError(f"O material {row.material_id} não tem fornecedor preferencial")
        by_supplier.setdefault(row.supplier_id, []).append(row)
    orders = []
    for supplier_id, rows in by_supplier.items():
        from .sequences import formatted
        number = formatted(db, company_id, "purchase_order_auto", prefix=f"OC-AUTO-{date.today():%Y%m%d}-", width=3, period=date.today().strftime("%Y%m%d"))
        purchase = PurchaseOrder(company_id=company_id, supplier_id=supplier_id, order_no=number, order_date=date.today(), expected_date=min((row.needed_by for row in rows if row.needed_by), default=None), status="draft", notes="Gerada automaticamente a partir de faltas confirmadas")
        db.add(purchase)
        db.flush()
        total = 0.0
        for suggestion in rows:
            amount = float(suggestion.suggested_quantity or 0) * float(suggestion.estimated_unit_cost or 0)
            db.add(PurchaseOrderLine(company_id=company_id, purchase_order_id=purchase.id, material_id=suggestion.material_id, quantity=suggestion.suggested_quantity, unit_cost=suggestion.estimated_unit_cost, received_quantity=0))
            total += amount
            suggestion.purchase_order_id = purchase.id
            suggestion.status = "converted"
        purchase.total = round(total, 4)
        orders.append(purchase)
    db.flush()
    return orders


def scan_code(db: Session, company_id: int, code: str) -> dict:
    value = (code or "").strip()
    batch = db.query(ProductionBatch).filter(ProductionBatch.company_id == company_id, (ProductionBatch.barcode == value) | (ProductionBatch.batch_no == value)).first()
    if batch:
        order = db.get(ProductionOrder, batch.production_order_id)
        return {"kind": "batch", "record": model_to_dict(batch), "order": model_to_dict(order), "next_action": "production"}
    unit = db.query(FinishedGoodsUnit).filter(FinishedGoodsUnit.company_id == company_id, (FinishedGoodsUnit.barcode == value) | (FinishedGoodsUnit.package_code == value)).first()
    if unit:
        return {"kind": "finished_goods", "record": model_to_dict(unit), "next_action": "shipping" if unit.status == "available" else unit.status}
    rework = db.query(ReworkOrder).filter(ReworkOrder.company_id == company_id, (ReworkOrder.barcode == value) | (ReworkOrder.reference == value)).first()
    if rework:
        return {"kind": "rework", "record": model_to_dict(rework), "next_action": "rework"}
    raise ValueError("Código não reconhecido nesta empresa")


def reconcile_primavera(db: Session, company_id: int, remote_rows: list[dict]) -> dict:
    remote = {(str(row.get("entity_type")), str(row.get("reference"))): row for row in remote_rows}
    local_rows = []
    from ..models import CommercialDocument
    for doc in db.query(CommercialDocument).filter_by(company_id=company_id).all():
        local_rows.append(("document", doc.doc_no, float(doc.total or 0), sum(float(line.get("quantity") or 0) for line in (doc.lines or [])), doc.primavera_remote_id))
    results = []
    for entity_type, reference, value, quantity, remote_id in local_rows:
        other = remote.get((entity_type, reference)) or {}
        remote_value = float(other.get("value") or 0)
        remote_quantity = float(other.get("quantity") or 0)
        status = "matched" if other and abs(value - remote_value) <= 0.01 and abs(quantity - remote_quantity) <= 0.01 else "missing_remote" if not other else "difference"
        row = db.query(IntegrationReconciliation).filter_by(company_id=company_id, system="primavera", entity_type=entity_type, local_reference=reference).first()
        if not row:
            row = IntegrationReconciliation(company_id=company_id, system="primavera", entity_type=entity_type, local_reference=reference)
            db.add(row)
        row.remote_reference = other.get("remote_reference") or remote_id
        row.local_value, row.remote_value = value, remote_value
        row.local_quantity, row.remote_quantity = quantity, remote_quantity
        row.status, row.checked_at = status, datetime.now(timezone.utc)
        row.detail = {"difference_value": round(value - remote_value, 2), "difference_quantity": round(quantity - remote_quantity, 2)}
        results.append(row)
    db.flush()
    return {"items": [model_to_dict(row) for row in results], "matched": sum(row.status == "matched" for row in results), "differences": sum(row.status != "matched" for row in results)}
