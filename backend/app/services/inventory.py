import re
import unicodedata

from sqlalchemy.orm import Session

from fastapi import HTTPException

from ..models import (
    CommercialDocument, Company, InventoryMovement, ItemAlias, Material, ProductionMaterialRequirement,
    ProductionOrder, ProductionOrderVariant, PurchaseOrder, PurchaseOrderLine, StockLot, Style, StyleVariant,
    Supplier,
)


OUTGOING_TYPES = {"issue", "consume", "transfer_out", "adjustment_out"}
INCOMING_TYPES = {"receipt", "return", "transfer_in", "adjustment_in"}


def _slug_token(value, max_len):
    plain = unicodedata.normalize("NFKD", value or "")
    ascii_only = "".join(char for char in plain if not unicodedata.combining(char))
    return re.sub(r"[^A-Za-z0-9]+", "", ascii_only).upper()[:max_len]


def _slug_reference(value, max_len):
    """Como _slug_token, mas preserva hifens existentes (ex.: "SWEAT-HOOD")."""
    plain = unicodedata.normalize("NFKD", value or "")
    ascii_only = "".join(char for char in plain if not unicodedata.combining(char))
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", ascii_only).strip("-").upper()
    return cleaned[:max_len]


def _variant_key(value):
    return _slug_token(value, 999)


def _unique_variant_sku(db, company_id, base):
    value, suffix = base, 2
    while db.query(StyleVariant).filter_by(company_id=company_id, sku=value).first():
        value = f"{base}-{suffix}"
        suffix += 1
    return value


def ensure_variant(db, style, color, size) -> StyleVariant:
    """Encontra a variante cor/tamanho (por comparação sem acentos/maiusculas) ou cria uma nova."""
    color = (color or "").strip() or None
    size = (size or "").strip() or None
    color_key = _variant_key(color)
    size_key = _variant_key(size)
    existing = db.query(StyleVariant).filter_by(style_id=style.id, company_id=style.company_id).all()
    for row in existing:
        if _variant_key(row.color) == color_key and _variant_key(row.size) == size_key:
            return row
    base = f"{_slug_reference(style.reference, 40)}-{_slug_token(color, 3)}-{_slug_token(size, 6)}".strip("-")[:70]
    sku = _unique_variant_sku(db, style.company_id, base)
    variant = StyleVariant(
        company_id=style.company_id, style_id=style.id, sku=sku,
        color=color, size=size, active=True,
        custom_data={"source": "release_grade"},
    )
    db.add(variant)
    db.flush()
    return variant


def _material_by_code(db, company_id, code):
    return db.query(Material).filter_by(company_id=company_id, code=code).first()


def _sync_primavera_item(db, material):
    from .primavera_sync import queue_master_record
    try:
        company = db.get(Company, material.company_id)
        if not company:
            return
        result = queue_master_record(company, "materials", material)
        if result and result.get("status") == "sent":
            material.sync_status = "synced"
            material.primavera_id = material.primavera_id or material.code
        elif result:
            material.sync_status = result.get("status") or "queued"
        else:
            material.sync_status = "local"
    except Exception:
        material.sync_status = "failed"


def style_overview(db: Session, style: Style) -> dict:
    """Matriz cor×tamanho + resumo de stock/produção/compras para a ficha do artigo (Produto acabado)."""
    from .production_split import holdings

    variants = db.query(StyleVariant).filter_by(style_id=style.id).order_by(StyleVariant.id).all()
    codes = [v.sku for v in variants]
    materials_by_code = {}
    if codes:
        for material in db.query(Material).filter(Material.company_id == style.company_id, Material.code.in_(codes)).all():
            materials_by_code[material.code] = material
    material_ids = [material.id for material in materials_by_code.values()]

    stock_by_material: dict[int, dict] = {}
    if material_ids:
        for lot in db.query(StockLot).filter(StockLot.material_id.in_(material_ids)).all():
            bucket = stock_by_material.setdefault(lot.material_id, {"on_hand": 0.0, "reserved": 0.0})
            bucket["on_hand"] += float(lot.quantity or 0)
            bucket["reserved"] += float(lot.reserved or 0)

    orders = (
        db.query(ProductionOrder)
        .filter_by(company_id=style.company_id, style_id=style.id)
        .filter(ProductionOrder.status.notin_({"cancelled", "completed"}))
        .all()
    )
    in_production_by_variant: dict[int, float] = {}
    active_orders = 0
    for order in orders:
        stock = holdings(db, order)
        active = stock["internal"] + stock["external"] + stock["unassigned"] + stock["revista"]
        if active > 0.001:
            active_orders += 1
        for pov in db.query(ProductionOrderVariant).filter_by(production_order_id=order.id).all():
            in_production_by_variant[pov.variant_id] = in_production_by_variant.get(pov.variant_id, 0.0) + float(pov.quantity or 0)

    matrix_colors, matrix_sizes = [], []
    cells = {}
    for variant in variants:
        color, size = variant.color or "—", variant.size or "—"
        if color not in matrix_colors:
            matrix_colors.append(color)
        if size not in matrix_sizes:
            matrix_sizes.append(size)
        material = materials_by_code.get(variant.sku)
        bucket = stock_by_material.get(material.id, {"on_hand": 0.0, "reserved": 0.0}) if material else {"on_hand": 0.0, "reserved": 0.0}
        cells[f"{color}|{size}"] = {
            "variant_id": variant.id, "sku": variant.sku, "barcode": variant.barcode, "active": variant.active,
            "material_id": material.id if material else None,
            "sync_status": material.sync_status if material else None,
            "on_hand": round(bucket["on_hand"], 2), "reserved": round(bucket["reserved"], 2),
            "in_production": round(in_production_by_variant.get(variant.id, 0.0), 2),
        }

    total_on_hand = sum(bucket["on_hand"] for bucket in stock_by_material.values())
    total_reserved = sum(bucket["reserved"] for bucket in stock_by_material.values())
    real_costs = [material.unit_cost for material in materials_by_code.values() if material.unit_cost]
    avg_cost = round(sum(real_costs) / len(real_costs), 4) if real_costs else 0.0

    last_purchase_line = (
        db.query(PurchaseOrderLine)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(PurchaseOrderLine.material_id.in_(material_ids or [0]))
        .order_by(PurchaseOrder.order_date.desc())
        .first()
    ) if material_ids else None
    last_purchase_order = db.get(PurchaseOrder, last_purchase_line.purchase_order_id) if last_purchase_line else None

    last_movement = (
        db.query(InventoryMovement)
        .filter(InventoryMovement.stock_lot_id.in_(db.query(StockLot.id).filter(StockLot.material_id.in_(material_ids or [0]))))
        .order_by(InventoryMovement.movement_time.desc())
        .first()
    ) if material_ids else None

    active_suppliers = {material.supplier_id for material in materials_by_code.values() if material.supplier_id}

    return {
        "variant_matrix": {"colors": matrix_colors, "sizes": matrix_sizes, "cells": cells},
        "summary": {
            "stock_available": round(max(0.0, total_on_hand - total_reserved), 2),
            "in_production_qty": round(sum(in_production_by_variant.values()), 2),
            "in_production_orders": active_orders,
            "avg_cost": avg_cost,
            "last_purchase_price": last_purchase_line.unit_cost if last_purchase_line else None,
            "last_purchase_date": last_purchase_order.order_date.isoformat() if last_purchase_order and last_purchase_order.order_date else None,
            "last_movement_date": last_movement.movement_time.isoformat() if last_movement else None,
            "active_suppliers": len(active_suppliers),
        },
    }


def ensure_item_for_style(db, style) -> Material:
    """Cria ou reaproveita o artigo (Material) ligado ao modelo, com codigo == referencia."""
    existing = _material_by_code(db, style.company_id, style.reference)
    if existing:
        return existing
    material = Material(
        company_id=style.company_id,
        code=style.reference,
        name=style.description or style.reference,
        category="other",
        unit=style.base_unit or "un",
        item_type="M",
        vat_code="23",
        color=style.color,
        custom_data={"source": "style", "style_id": style.id},
    )
    db.add(material)
    db.flush()
    _sync_primavera_item(db, material)
    return material


def _find_material(db, company_id, item_key) -> Material | None:
    try:
        material = db.query(Material).filter_by(company_id=company_id, id=int(item_key)).first()
        if material:
            return material
    except (TypeError, ValueError):
        pass
    return _material_by_code(db, company_id, str(item_key))


def stock_board(db: Session, company_id: int) -> dict:
    """Vista agregada de stock: materias-primas, peca em curso (WIP) e produto acabado."""
    from .primavera import PrimaveraError, fetch_stock
    from .production_split import holdings
    from .production_stage import STAGE_LABEL, derive_stage

    shadow_sources = {"style", "variant"}
    materials = [
        m for m in db.query(Material).filter_by(company_id=company_id, active=True).all()
        if (m.custom_data or {}).get("source") not in shadow_sources
    ]

    stock_by_material: dict[int, dict] = {}
    for lot in db.query(StockLot).filter_by(company_id=company_id).all():
        bucket = stock_by_material.setdefault(lot.material_id, {"on_hand": 0.0, "reserved": 0.0})
        bucket["on_hand"] += float(lot.quantity or 0)
        bucket["reserved"] += float(lot.reserved or 0)

    requested_by_material: dict[int, float] = {}
    open_lines = (
        db.query(PurchaseOrderLine)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(PurchaseOrder.company_id == company_id, PurchaseOrder.status.in_({"draft", "sent", "partial"}))
        .all()
    )
    for line in open_lines:
        remaining = max(0.0, float(line.quantity or 0) - float(line.received_quantity or 0))
        if remaining > 0.001:
            requested_by_material[line.material_id] = requested_by_material.get(line.material_id, 0.0) + remaining

    raw_items = []
    for material in materials:
        bucket = stock_by_material.get(material.id, {"on_hand": 0.0, "reserved": 0.0})
        on_hand, reserved = bucket["on_hand"], bucket["reserved"]
        requested = requested_by_material.get(material.id, 0.0)
        if on_hand <= 0.001 and requested <= 0.001:
            continue
        raw_items.append({
            "material_id": material.id, "code": material.code, "name": material.name,
            "unit_price": material.unit_cost, "unit": material.unit,
            "on_hand": round(on_hand, 4), "reserved": round(reserved, 4),
            "available": round(max(0.0, on_hand - reserved), 4), "requested": round(requested, 4),
            "supplier_id": material.supplier_id, "warehouse": material.warehouse,
            "vat_code": material.vat_code, "in_primavera": bool(material.primavera_id),
        })
    raw_items.sort(key=lambda row: row["code"] or "")

    company = db.get(Company, company_id)
    try:
        primavera = fetch_stock(company) if company else {"ok": False, "error": "Empresa não encontrada"}
    except PrimaveraError as error:
        primavera = {"ok": False, "error": str(error)}

    orders = (
        db.query(ProductionOrder)
        .filter_by(company_id=company_id)
        .filter(ProductionOrder.status != "cancelled")
        .all()
    )
    wip_rows, finished_rows = [], []
    wip_pieces = finished_pieces = 0.0
    for order in orders:
        stock = holdings(db, order)
        active_wip = stock["internal"] + stock["external"] + stock["unassigned"]
        if active_wip <= 0.001 and stock["revista"] <= 0.001:
            continue
        style = db.get(Style, order.style_id) if order.style_id else None
        stage = order.current_stage or derive_stage(db, order)
        row = {
            "id": order.id, "order_no": order.order_no,
            "article_code": style.reference if style else "",
            "article_name": style.description if style else "",
            "stage": stage, "location": STAGE_LABEL.get(stage, stage),
        }
        if active_wip > 0.001 and order.status != "completed":
            reserved_mp = sum(
                float(req.reserved_quantity or 0)
                for req in db.query(ProductionMaterialRequirement).filter_by(production_order_id=order.id).all()
            )
            wip_rows.append({**row, "in_progress": round(active_wip, 2), "quantity": order.quantity or 0, "reserved_mp": round(reserved_mp, 2)})
            wip_pieces += active_wip
        if stock["revista"] > 0.001:
            packed = float((order.custom_data or {}).get("packed_quantity") or 0)
            finished_rows.append({**row, "packed": round(min(packed, stock["revista"]), 2)})
            finished_pieces += stock["revista"]

    return {
        "raw_items": raw_items, "primavera": primavera,
        "wip": wip_rows, "wip_pieces": round(wip_pieces, 2),
        "finished": finished_rows, "finished_pieces": round(finished_pieces, 2),
    }


def material_history(db: Session, company_id: int, item_key: str) -> dict:
    material = _find_material(db, company_id, item_key)
    if not material:
        raise HTTPException(404, "Artigo não encontrado")

    lots = (
        db.query(StockLot).filter_by(company_id=company_id, material_id=material.id)
        .order_by(StockLot.received_date.desc()).all()
    )
    on_hand = sum(float(lot.quantity or 0) for lot in lots)

    lines = (
        db.query(PurchaseOrderLine)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(PurchaseOrder.company_id == company_id, PurchaseOrderLine.material_id == material.id)
        .order_by(PurchaseOrder.order_date.desc())
        .all()
    )
    suppliers_by_id: dict[int, dict] = {}
    purchases = []
    for line in lines:
        order = db.get(PurchaseOrder, line.purchase_order_id)
        if not order:
            continue
        supplier = db.get(Supplier, order.supplier_id) if order.supplier_id else None
        purchases.append({
            "order_no": order.order_no, "order_date": order.order_date,
            "supplier_name": supplier.name if supplier else "—",
            "received_quantity": line.received_quantity, "quantity": line.quantity,
            "unit_cost": line.unit_cost, "expected_date": order.expected_date,
            "lead_days": (order.expected_date - order.order_date).days if order.expected_date and order.order_date else None,
            "status": order.status,
        })
        if supplier and supplier.id not in suppliers_by_id:
            suppliers_by_id[supplier.id] = {
                "name": supplier.name, "code": supplier.code,
                "preferred": supplier.id == material.supplier_id, "payment_terms": supplier.payment_terms,
                "lead_time_days": material.lead_time_days, "last_price": line.unit_cost,
                "last_order_no": order.order_no, "last_order_date": order.order_date, "notes": None,
            }
    if material.supplier_id and material.supplier_id not in suppliers_by_id:
        supplier = db.get(Supplier, material.supplier_id)
        if supplier:
            suppliers_by_id[supplier.id] = {
                "name": supplier.name, "code": supplier.code, "preferred": True,
                "payment_terms": supplier.payment_terms, "lead_time_days": material.lead_time_days,
                "last_price": None, "last_order_no": None, "last_order_date": None, "notes": None,
            }

    prices = [
        {"date": p["order_date"], "source": "purchase_order", "reference": p["order_no"],
         "supplier_name": p["supplier_name"], "unit_price": p["unit_cost"]}
        for p in purchases if p["unit_cost"]
    ][:20]
    last_price = prices[0]["unit_price"] if prices else material.unit_cost
    average_price = round(sum(p["unit_price"] for p in prices) / len(prices), 4) if prices else material.unit_cost

    documents = []
    for doc in (
        db.query(CommercialDocument).filter_by(company_id=company_id)
        .order_by(CommercialDocument.doc_date.desc()).limit(200).all()
    ):
        for entry in (doc.lines or []):
            if str(entry.get("material_id") or "") == str(material.id) or str(entry.get("code") or "").lower() == (material.code or "").lower():
                supplier = db.get(Supplier, doc.supplier_id) if doc.supplier_id else None
                documents.append({
                    "doc_no": doc.doc_no, "doc_date": doc.doc_date, "doc_type": doc.doc_type,
                    "supplier_name": supplier.name if supplier else "—",
                    "unit_price": entry.get("unit_cost") or entry.get("unit_price"),
                })
                break
    documents = documents[:20]

    movement_rows = []
    for mv in (
        db.query(InventoryMovement)
        .join(StockLot, StockLot.id == InventoryMovement.stock_lot_id)
        .filter(StockLot.company_id == company_id, StockLot.material_id == material.id)
        .order_by(InventoryMovement.movement_time.desc()).limit(20).all()
    ):
        order = db.get(ProductionOrder, mv.production_order_id) if mv.production_order_id else None
        lot = db.get(StockLot, mv.stock_lot_id)
        movement_rows.append({
            "movement_time": mv.movement_time, "movement_type": mv.movement_type, "quantity": mv.quantity,
            "reference": mv.reference, "order_no": order.order_no if order else None,
            "lot_no": lot.lot_no if lot else None,
        })

    aliases = [
        {"source_name": row.source_name, "source_code": row.source_code, "hits": row.hits}
        for row in db.query(ItemAlias).filter_by(company_id=company_id, material_id=material.id).order_by(ItemAlias.hits.desc()).all()
    ]

    lot_rows = []
    for lot in lots:
        supplier = db.get(Supplier, lot.supplier_id) if lot.supplier_id else None
        lot_rows.append({
            "lot_no": lot.lot_no, "received_date": lot.received_date,
            "supplier_name": supplier.name if supplier else "—",
            "location": lot.location, "quantity": lot.quantity, "unit_cost": lot.unit_cost,
        })

    return {
        "material": {
            "id": material.id, "code": material.code, "name": material.name, "unit": material.unit,
            "composition": material.composition, "warehouse": material.warehouse, "notes": material.notes or "",
        },
        "summary": {
            "last_price": last_price, "average_price": average_price,
            "lead_time_days": material.lead_time_days, "on_hand": round(on_hand, 4),
            "suppliers": len(suppliers_by_id),
        },
        "suppliers": list(suppliers_by_id.values()), "purchases": purchases[:20], "prices": prices,
        "documents": documents, "lots": lot_rows, "movements": movement_rows, "aliases": aliases,
    }


def save_material_notes(db: Session, company_id: int, item_key: str, notes: str) -> Material:
    material = _find_material(db, company_id, item_key)
    if not material:
        raise HTTPException(404, "Artigo não encontrado")
    material.notes = notes
    return material


def ensure_item_for_variant(db, variant, style=None) -> Material:
    """Cria ou reaproveita o artigo (Material) ligado a esta variante, mantendo o codigo == SKU."""
    existing = _material_by_code(db, variant.company_id, variant.sku)
    if existing:
        return existing
    name_parts = [part for part in [style.description if style else None, variant.color, variant.size] if part]
    material = Material(
        company_id=variant.company_id,
        code=variant.sku,
        name=" ".join(name_parts) or variant.sku,
        category="other",
        unit="un",
        item_type="M",
        vat_code="23",
        color=variant.color,
        custom_data={"source": "variant", "variant_id": variant.id, "style_id": variant.style_id},
    )
    db.add(material)
    db.flush()
    _sync_primavera_item(db, material)
    return material


def register_movement(db, *, company_id: int, user_id: int, payload) -> InventoryMovement:
    lot = db.query(StockLot).filter_by(id=payload.stock_lot_id).with_for_update().first()
    if not lot or lot.company_id != company_id:
        raise HTTPException(404, "Lote não encontrado")
    order = db.get(ProductionOrder, payload.production_order_id) if payload.production_order_id else None
    if payload.production_order_id and (not order or order.company_id != company_id):
        raise HTTPException(422, "A ordem de fabrico nao pertence a esta empresa")
    quantity = abs(payload.quantity)
    if payload.movement_type in OUTGOING_TYPES:
        requirements = db.query(ProductionMaterialRequirement).filter_by(
            production_order_id=order.id, material_id=lot.material_id,
        ).all() if order else []
        reserved_allocations = []
        reserved_for_order = 0.0
        for requirement in requirements:
            for index, allocation in enumerate(requirement.lots or []):
                if int(allocation.get("lot_id") or 0) != lot.id:
                    continue
                reserved = max(0.0, float(allocation.get("reserved_quantity") or 0))
                if reserved:
                    reserved_allocations.append((requirement, index, reserved))
                    reserved_for_order += reserved
        unreserved = max(0.0, float(lot.quantity or 0) - float(lot.reserved or 0))
        if unreserved + reserved_for_order + 1e-9 < quantity:
            raise HTTPException(409, "Stock insuficiente")
        to_release = min(quantity, reserved_for_order)
        for requirement, index, reserved in reserved_allocations:
            if to_release <= 1e-9:
                break
            used = min(reserved, to_release)
            allocations = [dict(item) for item in (requirement.lots or [])]
            allocations[index]["reserved_quantity"] = round(reserved - used, 6)
            allocations[index]["consumed_quantity"] = round(
                float(allocations[index].get("consumed_quantity") or 0) + used, 6
            )
            requirement.lots = allocations
            requirement.reserved_quantity = max(0.0, float(requirement.reserved_quantity or 0) - used)
            lot.reserved = max(0.0, float(lot.reserved or 0) - used)
            to_release -= used
        consumed_from_reservation = min(quantity, reserved_for_order) - to_release
        unattributed = max(0.0, quantity - consumed_from_reservation)
        for requirement in requirements:
            if unattributed <= 1e-9:
                break
            allocations = [dict(item) for item in (requirement.lots or [])]
            consumed = sum(float(item.get("consumed_quantity") or 0) for item in allocations)
            remaining_need = max(0.0, float(requirement.required_quantity or 0) - consumed)
            used = min(unattributed, remaining_need)
            if used <= 1e-9:
                continue
            allocation = next((item for item in allocations if int(item.get("lot_id") or 0) == lot.id), None)
            if allocation is None:
                allocation = {"lot_id": lot.id, "lot_no": lot.lot_no, "reserved_quantity": 0.0}
                allocations.append(allocation)
            allocation["consumed_quantity"] = round(
                float(allocation.get("consumed_quantity") or 0) + used, 6
            )
            requirement.lots = allocations
            unattributed -= used
        for requirement in requirements:
            consumed = sum(float(item.get("consumed_quantity") or 0) for item in (requirement.lots or []))
            if consumed + 1e-9 >= float(requirement.required_quantity or 0):
                requirement.status = "issued"
            elif consumed > 1e-9:
                requirement.status = "partially_issued"
            elif float(requirement.reserved_quantity or 0) > 1e-9:
                requirement.status = "reserved"
            elif float(requirement.shortage_quantity or 0) > 1e-9:
                requirement.status = "shortage"
            else:
                requirement.status = "available"
        signed_quantity = -quantity
    elif payload.movement_type in INCOMING_TYPES:
        signed_quantity = quantity
    else:
        raise HTTPException(422, "Tipo de movimento inválido")
    movement = InventoryMovement(
        company_id=company_id, stock_lot_id=lot.id,
        production_order_id=payload.production_order_id,
        movement_type=payload.movement_type, quantity=signed_quantity,
        unit_cost=lot.unit_cost, location_from=lot.location,
        location_to=payload.location_to, reference=payload.reference, user_id=user_id,
    )
    lot.quantity += signed_quantity
    if payload.location_to and payload.movement_type in {"transfer_in", "transfer_out"}:
        lot.location = payload.location_to
    db.add(movement)
    db.flush()
    return movement
