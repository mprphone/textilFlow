from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from ..models import (
    Customer, InventoryMovement, Material, ProductionBatch, ProductionEvent, ProductionMovement,
    ProductionLine, ProductionMaterialRequirement, ProductionOrder, PurchaseOrder,
    PurchaseOrderLine, QualityInspection, SalesOrder, SalesOrderLine, SewingPlan,
    Shipment, StockLot, Style, SubcontractJob, SubcontractService, Supplier,
    CuttingJob,
)
from .order_followup import (
    bom_material_needs, commercial_name, cost_sheet_for_order, followup_alerts, service_plan,
)
from .production_route import build_route_status
from .production_split import holdings, job_out
from .serialization import model_to_dict

SERVICE = {
    "sewing": "Confeção", "dyeing": "Tinturaria", "printing": "Estamparia", "embroidery": "Bordado",
    "laundry": "Lavandaria", "finishing": "Acabamento", "transport": "Transporte", "cutting": "Corte",
}
JOB_STATUS = {
    "planned": "A enviar", "sent": "No fornecedor", "partial": "Receção parcial",
    "received": "Recebido", "problem": "Incidência", "cancelled": "Anulado",
}
MAT_STATUS = {
    "reserved": "Reservada em stock", "available": "Disponível em stock", "shortage": "Em falta",
    "unlinked_material": "Sem material ligado", "unit_mismatch": "Unidade incompatível",
}


def _g(row, key, default=0):
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _job_rows(db: Session, jobs) -> list:
    rows = []
    for job in jobs:
        service = db.get(SubcontractService, job.subcontract_service_id)
        supplier = db.get(Supplier, job.supplier_id)
        rows.append({
            **model_to_dict(job),
            "out_quantity": job_out(job),
            "service_name": service.name if service else None,
            "supplier_name": supplier.name if supplier else None,
        })
    return rows


def _material_state(req, issued: float, ordered: float, received_po: float) -> str:
    needed = _g(req, "required_quantity") or 0
    if issued >= needed > 0:
        return "delivered_to_floor"
    if issued > 0:
        return "partial_issue"
    if (_g(req, "reserved_quantity") or 0) >= needed > 0:
        return "reserved"
    if received_po > 0 and received_po >= ordered > 0:
        return "po_received"
    if ordered > received_po:
        return "on_order"
    if (_g(req, "shortage_quantity") or 0) > 0 or _g(req, "status") == "shortage":
        return "shortage"
    status = _g(req, "status")
    if status in MAT_STATUS:
        return status
    return "pending"


def order_cockpit(db: Session, order: ProductionOrder) -> dict:
    style = db.get(Style, order.style_id)
    jobs = db.query(SubcontractJob).filter_by(production_order_id=order.id).all()
    stock = holdings(db, order, jobs)
    plans = [
        plan for plan in db.query(SewingPlan).filter_by(production_order_id=order.id, company_id=order.company_id).all()
        if plan.status not in {"cancelled"}
    ]
    requirements = db.query(ProductionMaterialRequirement).filter_by(production_order_id=order.id).order_by(ProductionMaterialRequirement.id).all()
    movements = db.query(InventoryMovement).filter_by(production_order_id=order.id).all()
    lot_ids = {row.stock_lot_id for row in movements if row.stock_lot_id}
    lots = {row.id: row for row in db.query(StockLot).filter(StockLot.id.in_(lot_ids)).all()} if lot_ids else {}
    issued_by_material = defaultdict(float)
    for mov in movements:
        lot = lots.get(mov.stock_lot_id)
        if not lot or not lot.material_id:
            continue
        if mov.movement_type in {"issue", "consume"}:
            issued_by_material[lot.material_id] += abs(mov.quantity or 0)
        elif mov.movement_type in {"return"}:
            issued_by_material[lot.material_id] -= abs(mov.quantity or 0)

    need_rows = [model_to_dict(row) for row in requirements] if requirements else bom_material_needs(db, order)
    material_ids = [row.get("material_id") for row in need_rows if row.get("material_id")]
    po_ordered, po_received = defaultdict(float), defaultdict(float)
    if material_ids:
        for line, purchase in db.query(PurchaseOrderLine, PurchaseOrder).join(
            PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id
        ).filter(
            PurchaseOrder.company_id == order.company_id,
            PurchaseOrder.status.notin_(["cancelled", "draft"]),
            PurchaseOrderLine.material_id.in_(material_ids),
        ).all():
            po_ordered[line.material_id] += line.quantity or 0
            po_received[line.material_id] += line.received_quantity or 0

    materials = []
    for req in need_rows:
        mid = req.get("material_id")
        material = db.get(Material, mid) if mid else None
        issued = max(0, issued_by_material.get(mid or 0, 0))
        ordered = po_ordered.get(mid or 0, 0)
        received_po = po_received.get(mid or 0, 0)
        shortage = req.get("shortage_quantity")
        if shortage is None:
            shortage = max(0.0, (req.get("required_quantity") or 0) - (req.get("available_quantity") or 0))
            req["shortage_quantity"] = round(shortage, 4)
        to_order = max(0.0, (req.get("required_quantity") or 0) - (req.get("available_quantity") or 0) - max(0.0, ordered - received_po))
        category = (req.get("material_category") or (material.category if material else "") or "").lower()
        cost_group = req.get("cost_group") or ("fabric" if category in {"fabric", "knit", "woven", "malha", "tecido"} else "accessories")
        state = _material_state(req, issued, ordered, received_po)
        materials.append({
            **req,
            "material_code": material.code if material else req.get("material_code"),
            "material_name": material.name if material else req.get("description"),
            "cost_group": cost_group,
            "issued_quantity": round(issued, 4),
            "ordered_quantity": round(ordered, 4),
            "po_received_quantity": round(received_po, 4),
            "to_order_quantity": round(to_order, 4),
            "state": state,
        })

    locations = []
    for job in jobs:
        qty = job_out(job)
        if qty <= 0 and job.status not in {"received", "problem"}:
            continue
        service = db.get(SubcontractService, job.subcontract_service_id)
        supplier = db.get(Supplier, job.supplier_id)
        locations.append({
            "kind": "external",
            "label": supplier.name if supplier else "Subcontrato",
            "detail": f"{SERVICE.get(service.category, service.name) if service else 'Serviço'} · {JOB_STATUS.get(job.status, job.status)}",
            "quantity": qty or job.quantity or 0,
            "status": job.status,
            "reference": job.reference,
            "expected_date": job.expected_date.isoformat() if job.expected_date else None,
        })
    for plan in plans:
        if plan.allocation_type != "internal" or not plan.line_id or (plan.quantity or 0) <= 0:
            continue
        if plan.status in {"cancelled", "completed", "backlog"}:
            continue
        line = db.get(ProductionLine, plan.line_id)
        locations.append({
            "kind": "internal",
            "label": line.name if line else "Confeção",
            "detail": "Confeção interna",
            "quantity": plan.quantity,
            "status": plan.status,
            "reference": plan.code,
        })
    if stock["revista"]:
        locations.append({"kind": "revista", "label": "Revista", "detail": "Peças revistadas · aguarda destino", "quantity": stock["revista"], "status": "revista"})
    if stock["shipped"]:
        locations.append({"kind": "shipped", "label": "Expedido", "detail": "Já saiu para o cliente", "quantity": stock["shipped"], "status": "shipped"})
    if not any(row["kind"] == "internal" for row in locations) and order.line_id and stock["unassigned"]:
        line = db.get(ProductionLine, order.line_id)
        locations.append({
            "kind": "internal",
            "label": line.name if line else "Confeção",
            "detail": "Confeção interna",
            "quantity": stock["unassigned"],
            "status": "internal",
        })
        stock = {**stock, "internal": stock["unassigned"], "unassigned": 0}
    elif stock["unassigned"]:
        locations.append({"kind": "unassigned", "label": "Por distribuir", "detail": "Ainda sem destino", "quantity": stock["unassigned"], "status": "unassigned"})

    customer_name = None
    sales_no = None
    delivery_date = order.planned_end
    sales = None
    sales_line = db.get(SalesOrderLine, order.sales_order_line_id) if order.sales_order_line_id else None
    shipped_docs = []
    if sales_line:
        sales = db.get(SalesOrder, sales_line.sales_order_id)
        if sales:
            sales_no = sales.order_no
            customer = db.get(Customer, sales.customer_id)
            customer_name = customer.name if customer else None
            delivery_date = sales_line.delivery_date or sales.delivery_date or order.planned_end
            shipped_docs = [
                {"shipment_no": row.shipment_no, "quantity": row.quantity, "status": row.status, "shipped_at": row.shipped_at.isoformat() if row.shipped_at else None}
                for row in db.query(Shipment).filter_by(sales_order_id=sales.id).all()
            ]

    sheet = cost_sheet_for_order(db, order)
    steps = service_plan(db, order, jobs, stock["internal"])
    events = db.query(ProductionEvent).filter_by(production_order_id=order.id).order_by(ProductionEvent.event_time.desc()).limit(12).all()
    inspections = db.query(QualityInspection).filter_by(production_order_id=order.id).all()
    alerts = followup_alerts(order, jobs, materials, events, steps, delivery_date, inspections)
    days_left = (delivery_date - date.today()).days if delivery_date else None
    fabric_pos = db.query(PurchaseOrder).filter_by(company_id=order.company_id, production_order_id=order.id).all()

    return {
        "order": {
            **model_to_dict(order),
            "reference": style.reference if style else "",
            "description": style.description if style else "",
            "customer_name": customer_name,
            "sales_order_no": sales_no,
            "delivery_date": delivery_date.isoformat() if delivery_date else None,
            "planned_end": order.planned_end.isoformat() if order.planned_end else None,
            "commercial_name": commercial_name(db, order, sales, sheet),
            "days_to_delivery": days_left,
        },
        "holdings": {key: stock[key] for key in ("internal", "external", "shipped", "revista", "finished_goods", "unassigned", "total")},
        "locations": locations,
        "materials": materials,
        "goods": [row for row in materials if row.get("cost_group") == "fabric"],
        "accessories": [row for row in materials if row.get("cost_group") != "fabric"],
        "services": steps,
        "alerts": alerts,
        "jobs": _job_rows(db, jobs),
        "batches": [model_to_dict(row) for row in db.query(ProductionBatch).filter_by(production_order_id=order.id).all()],
        "events": [model_to_dict(row) for row in events],
        "quality": [model_to_dict(row) for row in inspections],
        "subcontract_chain": build_route_status(db, order),
        "cutting": [model_to_dict(row) for row in db.query(CuttingJob).filter_by(production_order_id=order.id).all()],
        "fabric_purchases": [{"id": row.id, "order_no": row.order_no, "status": row.status, "total": row.total, "expected_date": row.expected_date.isoformat() if row.expected_date else None} for row in fabric_pos],
        "shipments": shipped_docs,
        "stock_movements": [model_to_dict(row) for row in movements],
        "production_movements": [model_to_dict(row) for row in db.query(ProductionMovement).filter_by(production_order_id=order.id).order_by(ProductionMovement.occurred_at.desc(), ProductionMovement.id.desc()).limit(150).all()],
        "material_requirements": materials,
    }
