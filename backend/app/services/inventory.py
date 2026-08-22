from fastapi import HTTPException

from ..models import (
    InventoryMovement, ProductionMaterialRequirement, ProductionOrder, StockLot,
)


OUTGOING_TYPES = {"issue", "consume", "transfer_out", "adjustment_out"}
INCOMING_TYPES = {"receipt", "return", "transfer_in", "adjustment_in"}


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
