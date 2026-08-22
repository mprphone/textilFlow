from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy.orm import Session

from ..models import (
    CuttingJob, Material, ProductionMaterialRequirement, ProductionOrder,
    PurchaseOrder, PurchaseOrderLine, StockLot, Supplier,
)
from .inventory import register_movement
from .order_followup import FABRIC, bom_material_needs
from .proposal_release import _round


AVAILABLE_LOT = {"available", "active", "open"}


def is_fabric_row(row) -> bool:
    category = ""
    group = ""
    if isinstance(row, dict):
        category = str(row.get("material_category") or "")
        group = str(row.get("cost_group") or "")
    else:
        category = str(getattr(row, "material_category", None) or "")
        group = ""
    return category.lower() in FABRIC or group == "fabric"


def _requirement_rows(db: Session, order: ProductionOrder) -> list:
    stored = db.query(ProductionMaterialRequirement).filter_by(production_order_id=order.id).all()
    if stored:
        return stored
    return bom_material_needs(db, order)


def _reserved_by_lot(db: Session, company_id: int, material_ids: list[int]) -> dict[int, float]:
    if not material_ids:
        return {}
    rows = db.query(
        ProductionMaterialRequirement.lots
    ).filter(
        ProductionMaterialRequirement.company_id == company_id,
        ProductionMaterialRequirement.material_id.in_(material_ids),
    ).all()
    totals: dict[int, float] = {}
    for (lots,) in rows:
        for allocation in lots or []:
            lot_id = int(allocation.get("lot_id") or 0)
            reserved = float(allocation.get("reserved_quantity") or 0)
            if lot_id and reserved > 0:
                totals[lot_id] = totals.get(lot_id, 0.0) + reserved
    return totals


def _live_cover(db: Session, company_id: int, material_id: int | None, order_id: int, required: float, reserved_by_lot: dict[int, float] | None = None) -> float:
    if not material_id:
        return 0.0
    lots = db.query(StockLot).filter_by(company_id=company_id, material_id=material_id).all()
    if reserved_by_lot is None:
        reserved_by_lot = _reserved_by_lot(db, company_id, [material_id])
    cover = 0.0
    for lot in lots:
        if (lot.status or "available").lower() not in AVAILABLE_LOT:
            continue
        free = max(0.0, float(lot.quantity or 0) - float(lot.reserved or 0))
        reserved_here = reserved_by_lot.get(lot.id, 0.0)
        cover += free + reserved_here
    return cover


def _fabric_status_for_order(db: Session, order: ProductionOrder, reserved_by_lot: dict[int, float]) -> dict:
    rows = [row for row in _requirement_rows(db, order) if is_fabric_row(row)]
    if not rows:
        return {"ready": True, "needed": 0.0, "covered": 0.0, "unit": "kg", "missing": 0.0, "label": "Sem malha na ficha", "rows": [], "issued": 0.0, "last_issue_doc": None}
    material_ids = {row.material_id if not isinstance(row, dict) else row.get("material_id") for row in rows}
    material_ids.discard(None)
    if not reserved_by_lot and material_ids:
        reserved_by_lot = _reserved_by_lot(db, order.company_id, list(material_ids))
    needed = 0.0
    covered = 0.0
    unit = "kg"
    detail = []
    for row in rows:
        required = float(row.required_quantity if not isinstance(row, dict) else row.get("required_quantity") or 0)
        material_id = row.material_id if not isinstance(row, dict) else row.get("material_id")
        unit = (row.unit if not isinstance(row, dict) else row.get("unit")) or unit
        have = _live_cover(db, order.company_id, material_id, order.id, required, reserved_by_lot) if material_id else 0.0
        needed += required
        covered += min(have, required)
        detail.append({"material_id": material_id, "required": required, "covered": min(have, required), "unit": unit})
    missing = max(0.0, needed - covered)
    ready = missing <= 0.001
    label = f"Malha em stock · { _round(needed, 2) } {unit}" if ready else f"Falta malha · { _round(missing, 2) } {unit}"
    issued = float((order.custom_data or {}).get("fabric_issued_to_cut") or 0)
    last_doc = ((order.custom_data or {}).get("fabric_issue_docs") or [None])[-1]
    return {
        "ready": ready, "needed": _round(needed, 4), "covered": _round(covered, 4), "unit": unit,
        "missing": _round(missing, 4), "label": label, "rows": detail,
        "issued": _round(issued, 4), "last_issue_doc": last_doc,
    }


def fabric_status(db: Session, order: ProductionOrder | None) -> dict:
    if not order:
        return {"ready": True, "needed": 0.0, "covered": 0.0, "unit": "kg", "missing": 0.0, "label": "Sem OF", "rows": [], "issued": 0.0, "last_issue_doc": None}
    return _fabric_status_for_order(db, order, {})


def fabric_status_map(db: Session, company_id: int, order_ids: list[int]) -> dict[int, dict]:
    ids = {item for item in order_ids if item}
    if not ids:
        return {}
    orders = db.query(ProductionOrder).filter(
        ProductionOrder.company_id == company_id,
        ProductionOrder.id.in_(ids),
    ).all()
    material_ids = set()
    for order in orders:
        for row in _requirement_rows(db, order):
            if is_fabric_row(row):
                mid = row.material_id if not isinstance(row, dict) else row.get("material_id")
                if mid:
                    material_ids.add(mid)
    reserved_by_lot = _reserved_by_lot(db, company_id, list(material_ids)) if material_ids else {}
    return {order.id: _fabric_status_for_order(db, order, reserved_by_lot) for order in orders}


def assert_fabric_in_stock(db: Session, order: ProductionOrder | None, *, stage: str):
    status = fabric_status(db, order)
    if status["ready"]:
        return status
    where = "corte" if stage == "cutting" else "confeção"
    raise ValueError(
        f"Não dá para planear {where}: a malha ainda não está em stock. "
        f"{status['label']}. Dê entrada da encomenda de malha ou reserve o que já tem."
    )


def sewing_ready_status(db: Session, order: ProductionOrder | None) -> dict:
    if not order:
        return {"ready": True, "label": "Sem OF", "missing": "corte"}
    status = fabric_status(db, order)
    if not status["needed"]:
        return {"ready": True, "label": "Artigo sem malha · pode costurar diretamente", "missing": None}
    job = db.query(CuttingJob).filter_by(company_id=order.company_id, production_order_id=order.id).order_by(CuttingJob.id.desc()).first()
    if not job:
        return {"ready": False, "label": "Corte ainda não planeado", "missing": "corte"}
    if float(job.actual_fabric or 0) <= 0.001:
        return {"ready": False, "label": "Malha ainda não saiu do armazém para corte", "missing": "fabric_issue"}
    if float(job.good_pieces or 0) <= 0.001 and job.status not in {"in_progress", "completed"}:
        return {"ready": False, "label": "Corte ainda não produziu peças", "missing": "cutting"}
    return {"ready": True, "label": f"Corte ok · {job.actual_fabric} {status['unit']} de malha · {job.good_pieces} peças", "missing": None, "job": job}


def assert_sewing_ready(db: Session, order: ProductionOrder | None, *, override: bool = False):
    status = sewing_ready_status(db, order)
    if status["ready"] or override:
        return status
    raise ValueError(
        f"Não dá para planear confeção: {status['label']}. "
        "A OF tem de passar pelo corte primeiro."
    )


def fabric_delay_risk(db: Session, order: ProductionOrder) -> dict:
    status = fabric_status(db, order)
    if not order or status["ready"] or status["missing"] <= 0.001:
        return {"at_risk": False, "days_late": 0, "expected_arrival": None, "reason": ""}
    pos = db.query(PurchaseOrder).filter_by(company_id=order.company_id, production_order_id=order.id).all()
    pos = [row for row in pos if row.status not in {"cancelled", "completed"}]
    if not pos:
        return {"at_risk": True, "days_late": None, "expected_arrival": None, "reason": "Sem encomenda de malha registada"}
    expected_dates = [row.expected_date for row in pos if row.expected_date]
    earliest = min(expected_dates) if expected_dates else None
    if earliest:
        lead = (earliest - date.today()).days
    else:
        leads = []
        for row in pos:
            supplier = db.get(Supplier, row.supplier_id) if row.supplier_id else None
            if supplier and supplier.lead_time_days:
                leads.append(supplier.lead_time_days)
        lead = min(leads) if leads else None
        earliest = date.today() + timedelta(days=lead) if lead is not None else None
    cutting_start = order.planned_start
    job = db.query(CuttingJob).filter_by(company_id=order.company_id, production_order_id=order.id).order_by(CuttingJob.id.desc()).first()
    if job and job.started_at:
        cutting_start = job.started_at.date()
    elif job and job.end_date:
        cutting_start = job.end_date
    if not cutting_start and order.delivery_date:
        cutting_start = order.delivery_date - timedelta(days=7)
    days_late = None
    if earliest and cutting_start:
        days_late = (earliest - cutting_start).days
    at_risk = days_late is not None and days_late > 0
    return {
        "at_risk": at_risk,
        "days_late": days_late,
        "expected_arrival": earliest.isoformat() if earliest else None,
        "reason": f"Malha prevista para {earliest.isoformat() if earliest else 'n/d'} · corte necessário a partir de {cutting_start.isoformat() if cutting_start else 'n/d'}",
    }


def _fallback_supplier(db: Session, company_id: int) -> Supplier:
    existing = (
        db.query(Supplier)
        .filter(Supplier.company_id == company_id, Supplier.active.is_(True))
        .order_by(Supplier.id)
        .all()
    )
    for row in existing:
        kind = f"{row.supplier_type or ''} {row.name or ''}".lower()
        if any(token in kind for token in ("material", "fabric", "malha", "tecid")):
            return row
    if existing:
        return existing[0]
    supplier = Supplier(
        company_id=company_id, code="MALHA-INT", name="Fornecedor de malha",
        supplier_type="material", lead_time_days=10, active=True,
    )
    db.add(supplier)
    db.flush()
    return supplier


def _unique_po(db: Session, company_id: int, base: str) -> str:
    value = base
    suffix = 2
    while db.query(PurchaseOrder).filter_by(company_id=company_id, order_no=value).first():
        value = f"{base}-{suffix}"
        suffix += 1
    return value


def create_fabric_purchases(db: Session, order: ProductionOrder, requirements: list) -> list[PurchaseOrder]:
    shortages = []
    for row in requirements:
        if not is_fabric_row(row):
            continue
        missing = float(row.shortage_quantity or 0)
        if missing <= 0.001:
            continue
        shortages.append(row)
    if not shortages:
        data = dict(order.custom_data or {})
        data["fabric_ready"] = True
        data["fabric_purchase_orders"] = []
        order.custom_data = data
        return []
    grouped: dict[int, list] = defaultdict(list)
    for row in shortages:
        material = db.get(Material, row.material_id) if row.material_id else None
        supplier = db.get(Supplier, material.supplier_id) if material and material.supplier_id else None
        supplier = supplier or _fallback_supplier(db, order.company_id)
        grouped[supplier.id].append((row, material, supplier))
    created = []
    for supplier_id, items in grouped.items():
        supplier = items[0][2]
        po = PurchaseOrder(
            company_id=order.company_id,
            supplier_id=supplier.id,
            order_no=_unique_po(db, order.company_id, f"MALHA-{order.order_no}"),
            order_date=date.today(),
            expected_date=date.today() + timedelta(days=supplier.lead_time_days or 10),
            status="sent",
            notes=f"Necessidade de malha da OF {order.order_no}",
            production_order_id=order.id,
        )
        db.add(po)
        db.flush()
        total = 0.0
        for row, material, _supplier in items:
            qty = float(row.shortage_quantity or 0)
            cost = float((material.unit_cost if material else 0) or row.average_unit_cost or 0)
            db.add(PurchaseOrderLine(
                company_id=order.company_id, purchase_order_id=po.id,
                material_id=row.material_id, quantity=qty, unit_cost=cost, received_quantity=0,
            ))
            total += qty * cost
            row.status = "on_order"
        po.total = _round(total, 2)
        created.append(po)
    data = dict(order.custom_data or {})
    data["fabric_ready"] = False
    data["fabric_purchase_orders"] = [{"id": row.id, "order_no": row.order_no} for row in created]
    order.custom_data = data
    order.current_stage = "à espera de malha"
    return created


def refresh_order_fabric(db: Session, order: ProductionOrder | None):
    if not order:
        return None
    requirements = db.query(ProductionMaterialRequirement).filter_by(production_order_id=order.id).all()
    for req in requirements:
        if not req.material_id:
            continue
        lots = db.query(StockLot).filter_by(company_id=order.company_id, material_id=req.material_id).all()
        free = 0.0
        for lot in lots:
            if (lot.status or "available").lower() not in AVAILABLE_LOT:
                continue
            free += max(0.0, float(lot.quantity or 0) - float(lot.reserved or 0))
        still = max(0.0, float(req.required_quantity or 0) - float(req.reserved_quantity or 0) - free)
        req.available_quantity = _round(free + float(req.reserved_quantity or 0), 4)
        req.shortage_quantity = _round(still, 4)
        if still <= 0.001:
            req.status = "reserved" if req.reserved_quantity else "available"
        elif float(req.shortage_quantity or 0) > 0.001:
            req.status = "shortage" if req.status not in {"on_order"} else req.status
    status = fabric_status(db, order)
    data = dict(order.custom_data or {})
    data["fabric_ready"] = status["ready"]
    order.custom_data = data
    if status["ready"] and (order.current_stage or "") in {"planning", "à espera de malha", "backlog"}:
        order.current_stage = "malha em stock"
    from .production_stage import update_order_stage
    update_order_stage(db, order)
    return status


def refresh_fabric_after_receipt(db: Session, purchase: PurchaseOrder):
    if not purchase.production_order_id:
        return
    refresh_order_fabric(db, db.get(ProductionOrder, purchase.production_order_id))


def push_fabric_alert(order: ProductionOrder, *, title: str, detail: str, level: str = "info") -> dict:
    data = dict(order.custom_data or {})
    alert = {
        "at": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "title": title,
        "detail": detail,
        "order_no": order.order_no,
        "seen": False,
    }
    alerts = list(data.get("fabric_alerts") or [])
    alerts.append(alert)
    data["fabric_alerts"] = alerts[-20:]
    order.custom_data = data
    return alert


def orders_waiting_malha(db: Session, company_id: int, material_ids: list[int] | None = None) -> list[ProductionOrder]:
    query = db.query(ProductionMaterialRequirement).filter(
        ProductionMaterialRequirement.company_id == company_id,
    )
    if material_ids:
        query = query.filter(ProductionMaterialRequirement.material_id.in_(material_ids or [-1]))
    order_ids = {
        row.production_order_id for row in query.all()
        if row.production_order_id and (
            float(row.shortage_quantity or 0) > 0.001
            or (row.status or "") in {"shortage", "on_order"}
        )
    }
    if not order_ids:
        return []
    return db.query(ProductionOrder).filter(
        ProductionOrder.company_id == company_id,
        ProductionOrder.id.in_(order_ids),
        ProductionOrder.status.notin_(["completed", "cancelled"]),
    ).all()


def notify_fabric_receipt(db: Session, company_id: int, *, purchase: PurchaseOrder | None = None, material_ids: list[int] | None = None, source_no: str = "") -> list[dict]:
    waiting = []
    if purchase and purchase.production_order_id:
        order = db.get(ProductionOrder, purchase.production_order_id)
        if order:
            waiting = [order]
    extra = orders_waiting_malha(db, company_id, material_ids)
    by_id = {row.id: row for row in waiting}
    for order in extra:
        by_id[order.id] = order
    waiting = list(by_id.values())
    seen = set()
    alerts = []
    ref = source_no or (purchase.order_no if purchase else "entrada")
    for order in waiting:
        if order.id in seen:
            continue
        seen.add(order.id)
        before = fabric_status(db, order)
        refresh_order_fabric(db, order)
        status = fabric_status(db, order)
        if not before["ready"] or status["ready"] or status["covered"] > before["covered"]:
            if status["ready"]:
                alert = push_fabric_alert(
                    order,
                    title=f"Malha deu entrada · {order.order_no}",
                    detail=f"{ref}: a malha da OF {order.order_no} já está em stock. Pode criar a saída para o corte.",
                    level="info",
                )
            else:
                alert = push_fabric_alert(
                    order,
                    title=f"Entrada de malha · {order.order_no}",
                    detail=f"{ref}: entrou malha para {order.order_no}. {status['label']}. A OF pode continuar no plano.",
                    level="warning",
                )
            alerts.append(alert)
    return alerts


def consume_fabric_for_cutting(db: Session, *, company_id: int, user_id: int | None, order: ProductionOrder, quantity: float) -> dict:
    qty = abs(float(quantity or 0))
    if qty <= 1e-9:
        raise ValueError("Indique quantos kg (ou metros) de malha vão para o corte.")
    status = fabric_status(db, order)
    if not status["ready"]:
        raise ValueError(
            f"{status['label']}. Sem malha em stock não há saída nem corte. "
            "Dê entrada da encomenda de malha ou reserve o que já tem no armazém."
        )
    remaining = qty
    fabric_ids = [row["material_id"] for row in status["rows"] if row.get("material_id")]
    lots = db.query(StockLot).filter(
        StockLot.company_id == company_id, StockLot.material_id.in_(fabric_ids or [-1]),
    ).order_by(StockLot.id).all()
    reserved_first = []
    free_next = []
    reqs = db.query(ProductionMaterialRequirement).filter_by(production_order_id=order.id).all()
    reserved_lot_ids = set()
    for req in reqs:
        for allocation in req.lots or []:
            if float(allocation.get("reserved_quantity") or 0) > 0:
                reserved_lot_ids.add(int(allocation.get("lot_id") or 0))
    for lot in lots:
        if lot.id in reserved_lot_ids:
            reserved_first.append(lot)
        else:
            free_next.append(lot)
    taken = 0.0
    movements = []
    for lot in reserved_first + free_next:
        if remaining <= 1e-9:
            break
        free = max(0.0, float(lot.quantity or 0) - float(lot.reserved or 0))
        available = free
        if lot.id in reserved_lot_ids:
            available += sum(
                float(allocation.get("reserved_quantity") or 0)
                for req in reqs
                for allocation in (req.lots or [])
                if int(allocation.get("lot_id") or 0) == lot.id
            )
        take = min(available, remaining)
        if take <= 1e-9:
            continue
        movements.append((lot, take))
        remaining -= take
        taken += take
    if remaining > 0.01:
        raise ValueError(
            f"Stock insuficiente para esta saída. Só há {_round(taken, 2)} {status['unit']} disponíveis. "
            f"Faltam {_round(remaining, 2)} {status['unit']}."
        )
    from .commercial_docs import create_document
    lines = []
    for lot, take in movements:
        material = db.get(Material, lot.material_id)
        lines.append({
            "material_id": lot.material_id,
            "quantity": take,
            "unit_cost": lot.unit_cost or 0,
            "unit": material.unit if material else status["unit"],
            "description": material.name if material else "Malha",
            "code": material.code if material else "",
            "lot": lot.lot_no,
            "warehouse": lot.location or "Armazém",
        })
    document = create_document(db, company_id, {
        "doc_type": "fabric_issue",
        "status": "issued",
        "sales_order_id": None,
        "notes": f"Saída de malha para corte · OF {order.order_no}",
        "lines": lines,
        "extra": {
            "production_order_id": order.id,
            "order_no": order.order_no,
            "destination": "Corte",
            "locked": False,
            "official": False,
        },
    })
    document.status = "issued"
    document.primavera_status = "internal"
    extra = dict(document.extra or {})
    extra["production_order_id"] = order.id
    extra["destination"] = "Corte"
    document.extra = extra
    for lot, take in movements:
        register_movement(db, company_id=company_id, user_id=user_id, payload=SimpleNamespace(
            stock_lot_id=lot.id, movement_type="issue", quantity=take,
            production_order_id=order.id, location_to="Corte", reference=document.doc_no,
        ))
    job = db.query(CuttingJob).filter_by(company_id=company_id, production_order_id=order.id).order_by(CuttingJob.id.desc()).first()
    if not job:
        job = CuttingJob(
            company_id=company_id, production_order_id=order.id, status="in_progress",
            planned_pieces=order.quantity or 0,
        )
        db.add(job)
    job.actual_fabric = float(job.actual_fabric or 0) + taken
    job.planned_fabric = float(job.planned_fabric or 0) or status["needed"]
    data = dict(order.custom_data or {})
    data["fabric_issued_to_cut"] = _round(float(data.get("fabric_issued_to_cut") or 0) + taken, 4)
    docs = list(data.get("fabric_issue_docs") or [])
    docs.append({"id": document.id, "doc_no": document.doc_no, "quantity": _round(taken, 4)})
    data["fabric_issue_docs"] = docs
    order.custom_data = data
    from .production_stage import update_order_stage
    update_order_stage(db, order)
    return {"taken": taken, "doc_no": document.doc_no, "document_id": document.id, "unit": status["unit"]}


def gate_and_maybe_consume(db, *, company_id: int, user_id: int | None, order: ProductionOrder | None, stage: str, first_day: bool, fabric_quantity: float | None):
    if not order:
        return None
    if stage != "cutting":
        return None
    status = fabric_status(db, order)
    qty = abs(float(fabric_quantity or 0))
    if not status["ready"]:
        if qty > 0:
            data = dict(order.custom_data or {})
            data["fabric_planned_to_cut"] = _round(qty, 4)
            order.custom_data = data
        return {"waiting_stock": True, "planned": qty, "unit": status["unit"], "label": status["label"]}
    if qty <= 0:
        return None
    return consume_fabric_for_cutting(db, company_id=company_id, user_id=user_id, order=order, quantity=qty)
