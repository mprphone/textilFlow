from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import CuttingJob, ProductionBatch, ProductionMovement, ProductionOrder, ProductionOrderVariant, QualityInspection, SalesOrderLine, SewingPlan, Shipment, StyleVariant, SubcontractJob, SubcontractService
from .fabric_flow import fabric_status
from .kanban import KANBAN_WAITING


STAGE_ORDER = ["planning", "à espera de malha", "malha em stock", "corte", "confeção", "acabamento", "expedição", "completed"]
STAGE_LABEL = {
    "planning": "Planeamento",
    "à espera de malha": "À espera de malha",
    "malha em stock": "Malha em stock",
    "corte": "Corte",
    "confeção": "Confeção",
    "acabamento": "Acabamento",
    "expedição": "Expedição",
    "production": "Em produção",
    "completed": "Concluída",
}


def _has_fabric_requirement(db: Session, order: ProductionOrder) -> bool:
    status = fabric_status(db, order)
    return status["needed"] > 0.001


def _cutting_state(db: Session, order: ProductionOrder) -> tuple[str, dict | None]:
    jobs = (
        db.query(CuttingJob)
        .filter_by(company_id=order.company_id, production_order_id=order.id)
        .order_by(CuttingJob.id.desc())
        .all()
    )
    if not jobs:
        return "not_started", None
    latest = jobs[0]
    good_pieces = sum(float(job.good_pieces or 0) for job in jobs)
    all_closed = all(job.status in {"completed", "done", "cancelled"} for job in jobs)
    if all_closed or good_pieces >= float(order.quantity or 0) * 0.99:
        return "completed", latest
    if any(float(job.actual_fabric or 0) > 0.001 or float(job.good_pieces or 0) > 0.001 for job in jobs):
        return "in_progress", latest
    return "planned", latest


def _sewing_state(db: Session, order: ProductionOrder) -> tuple[str, int]:
    plans = (
        db.query(SewingPlan)
        .filter_by(company_id=order.company_id, production_order_id=order.id)
        .all()
    )
    internal_plans = [row for row in plans if row.allocation_type == "internal" and row.line_id]
    if not internal_plans:
        return "not_planned", 0
    total_planned = sum(float(row.quantity or 0) for row in internal_plans)
    return "planned", total_planned


def _external_services_open(db: Session, order: ProductionOrder) -> list[str]:
    open_jobs = (
        db.query(SubcontractJob)
        .filter_by(company_id=order.company_id, production_order_id=order.id)
        .filter(SubcontractJob.status.in_({"planned", "sent", "partial", "in_progress"}))
        .all()
    )
    categories = []
    for job in open_jobs:
        service = db.get(SubcontractService, job.subcontract_service_id) if job.subcontract_service_id else None
        categories.append((service.category if service else "") or "")
    return categories


def derive_stage(db: Session, order: ProductionOrder) -> str:
    if order.status == "cancelled":
        return "cancelled"
    data = order.custom_data or {}
    target = float(order.quantity or 0)
    produced = float(order.completed_quantity or 0)
    packed = float(data.get("packed_quantity") or 0)
    shipped = float(data.get("shipped_quantity") or 0)
    if target > 0 and shipped >= target - 0.001:
        return "completed"
    if packed > shipped + 0.001:
        return "expedição"
    if target > 0 and produced >= target * 0.99:
        return "acabamento"

    has_fabric = _has_fabric_requirement(db, order)
    fabric_status_result = fabric_status(db, order)
    cutting_state, _job = _cutting_state(db, order)
    sewing_state, _sewing_qty = _sewing_state(db, order)

    # Se já está em expedição, mantém até concluir
    if (order.current_stage or "").lower() == "expedição" and not order.completed_quantity:
        return "expedição"

    if not has_fabric:
        # Artigo sem malha (ex: feitio, acessórios apenas)
        if sewing_state == "planned":
            return "confeção"
        return "planning"

    if fabric_status_result["ready"] and cutting_state == "not_started":
        return "malha em stock"

    if cutting_state == "in_progress":
        return "corte"

    if cutting_state == "completed":
        if sewing_state == "planned":
            return "confeção"
        if _external_services_open(db, order):
            return "acabamento" if any(s in {"printing", "embroidery", "dyeing", "finishing"} for s in _external_services_open(db, order)) else "confeção"
        return "corte"

    if fabric_status_result["ready"]:
        return "malha em stock"

    return "à espera de malha"


def create_batches_from_cutting(db: Session, job: CuttingJob) -> list[ProductionBatch]:
    if not job or not job.production_order_id or float(job.good_pieces or 0) <= 0.001:
        return []
    order = db.get(ProductionOrder, job.production_order_id)
    if not order:
        return []
    pieces = int(job.good_pieces or 0)
    if pieces <= 0:
        return []
    prefix = f"{order.order_no}-CORTE-{job.id}"
    variants = (
        db.query(ProductionOrderVariant, StyleVariant)
        .join(StyleVariant, StyleVariant.id == ProductionOrderVariant.variant_id)
        .filter(ProductionOrderVariant.production_order_id == order.id)
        .order_by(ProductionOrderVariant.id)
        .all()
    )
    created = []
    if variants:
        all_batches = db.query(ProductionBatch).filter_by(company_id=order.company_id, production_order_id=order.id).all()
        remaining_pieces = pieces
        for planned, variant in variants:
            batch_no = f"{prefix}-{variant.id}"
            batch = next((row for row in all_batches if row.batch_no == batch_no), None)
            other_quantity = sum(
                float(row.quantity or 0) for row in all_batches
                if row.id != getattr(batch, "id", None) and row.color == variant.color and row.size == variant.size
            )
            available_for_variant = max(0, float(planned.quantity or 0) - other_quantity)
            target = min(remaining_pieces, available_for_variant)
            if target <= 0:
                continue
            if not batch:
                batch = ProductionBatch(
                    company_id=order.company_id, production_order_id=order.id, batch_no=batch_no,
                    variant_id=variant.id, source_cutting_job_id=job.id,
                    color=variant.color, size=variant.size, completed_quantity=0,
                    current_location="Corte", status="waiting", kanban_status=KANBAN_WAITING,
                )
                db.add(batch)
                created.append(batch)
            batch.quantity = max(float(batch.quantity or 0), target)
            remaining_pieces -= target
            if remaining_pieces <= 0:
                break
    else:
        batch = db.query(ProductionBatch).filter_by(
            company_id=order.company_id, production_order_id=order.id, batch_no=prefix
        ).first()
        other_quantity = sum(
            float(row.quantity or 0)
            for row in db.query(ProductionBatch).filter_by(company_id=order.company_id, production_order_id=order.id).all()
            if row.id != getattr(batch, "id", None)
        )
        target = min(pieces, max(0, float(order.quantity or 0) - other_quantity))
        if target <= 0:
            return []
        if not batch:
            batch = ProductionBatch(
                company_id=order.company_id, production_order_id=order.id, batch_no=prefix,
                source_cutting_job_id=job.id,
                color=job.fabric_lot or "", completed_quantity=0,
                current_location="Corte", status="waiting", kanban_status=KANBAN_WAITING,
            )
            db.add(batch)
            created.append(batch)
        batch.quantity = max(float(batch.quantity or 0), target)
    db.flush()
    affected = db.query(ProductionBatch).filter(
        ProductionBatch.company_id == order.company_id,
        ProductionBatch.production_order_id == order.id,
        ProductionBatch.batch_no.like(f"{prefix}%"),
    ).all()
    for batch in affected:
        if db.query(QualityInspection).filter_by(company_id=order.company_id, batch_id=batch.id, inspection_type="incoming_cut").first():
            continue
        inspection = QualityInspection(
            company_id=order.company_id,
            production_order_id=order.id,
            batch_id=batch.id,
            inspection_type="incoming_cut",
            inspected_quantity=batch.quantity,
            result="pending",
            notes="Corte concluído · aguarda inspeção de entrada.",
        )
        db.add(inspection)
    return created or affected


def assert_subcontract_ready(db: Session, order: ProductionOrder, service, *, override: bool = False) -> dict:
    """Regras de bom-senso independentes de sequência (sempre aplicadas) + fallback legado.

    A restrição fixa "corte tem de começar antes de qualquer subcontrato" só se
    aplica quando o artigo NÃO tem uma sequência de produção configurada
    (`ProductionRouteStep`) — nesse caso a ordem entre corte, confeção e
    subcontratos (ex.: tingir a malha antes de cortar, ou confecionar a peça
    antes de a mandar tingir) vem inteiramente da configuração, não daqui.
    """
    if not order or not service:
        return {"ready": True, "reason": ""}
    category = (service.category or "").lower()
    fabric = fabric_status(db, order)
    if category in {"cutting"} and not fabric["ready"]:
        return {"ready": override, "reason": f"Malha ainda não está em stock para mandar cortar fora: {fabric['label']}"}
    from .production_route import route_for_style
    if route_for_style(db, order.style_id):
        return {"ready": True, "reason": ""}
    cutting = _cutting_state(db, order)
    if category in {"dyeing", "printing", "embroidery", "laundry", "finishing", "sewing"} and cutting[0] in {"not_started", "planned"}:
        return {"ready": override, "reason": "Corte ainda não iniciado. Só envia para subcontrato depois de cortar."}
    return {"ready": True, "reason": ""}


def ensure_final_quality_checkpoint(db: Session, order: ProductionOrder) -> QualityInspection | None:
    if not order:
        return None
    produced = float(order.completed_quantity or 0)
    target = float(order.quantity or 0)
    if produced <= 0.001 or produced + 0.001 < target:
        return None
    if db.query(QualityInspection).filter_by(company_id=order.company_id, production_order_id=order.id, inspection_type="final").first():
        return None
    inspection = QualityInspection(
        company_id=order.company_id,
        production_order_id=order.id,
        inspection_type="final",
        inspected_quantity=produced,
        result="pending",
        notes="Produção concluída · aguarda inspeção final antes da expedição.",
    )
    db.add(inspection)
    db.flush()
    return inspection


def dispatch_ready_status(db: Session, sales_order) -> dict:
    # Compatibilidade para consumidores existentes. A regra completa vive no
    # serviço de expedição e calcula saldos parciais por linha e por OF.
    from .shipping import dispatch_status
    return dispatch_status(db, sales_order)


def record_revista(db: Session, order: ProductionOrder, payload: dict) -> QualityInspection:
    """Regista o resultado da inspeção de revista — não move quantidade entre
    áreas (isso é sempre o /distribute, source=internal/external, destination=revista)."""
    from .production_split import revista_qty
    quantity = float(payload.get("quantity") or revista_qty(order) or 0)
    if quantity <= 0.001:
        raise ValueError("Indique a quantidade revistada")
    defect_quantity = float(payload.get("defect_quantity") or 0)
    result = payload.get("result") or ("failed" if defect_quantity > 0.001 else "passed")
    inspection = QualityInspection(
        company_id=order.company_id,
        production_order_id=order.id,
        inspection_type="revista",
        inspected_quantity=quantity,
        defect_quantity=defect_quantity,
        defect_code=payload.get("defect_code"),
        result=result,
        notes=payload.get("notes"),
    )
    db.add(inspection)
    db.flush()
    from .execution import sync_quality_movement
    sync_quality_movement(db, inspection, payload.get("user_id"))
    from .operations_control import ensure_rework_for_inspection
    ensure_rework_for_inspection(db, inspection, payload.get("user_id"))
    update_order_stage(db, order)
    return inspection


def record_packing(db: Session, order: ProductionOrder, payload: dict) -> dict:
    """Move peças aprovadas da revista para produto acabado."""
    from .production_split import holdings, revista_qty
    from .shipping import approved_quantity
    quantity = float(payload.get("quantity") or 0)
    if quantity <= 0.001:
        raise ValueError("Indique a quantidade embalada")
    variant_id = int(payload.get("variant_id") or 0) or None
    order_variants = db.query(ProductionOrderVariant).filter_by(production_order_id=order.id).order_by(ProductionOrderVariant.id).all()
    if not variant_id and len(order_variants) == 1:
        variant_id = order_variants[0].variant_id
    if not variant_id and len(order_variants) > 1:
        raise ValueError("Selecione a cor e o tamanho que estão a ser embalados")
    if not variant_id and order.sales_order_line_id:
        sales_line = db.get(SalesOrderLine, order.sales_order_line_id)
        variant_id = sales_line.variant_id if sales_line else None
    batch_id = int(payload.get("batch_id") or 0) or None
    eligible_batches = db.query(ProductionBatch).filter_by(
        company_id=order.company_id, production_order_id=order.id,
    ).filter(ProductionBatch.status != "cancelled").order_by(ProductionBatch.id).all()
    if variant_id:
        eligible_batches = [row for row in eligible_batches if row.variant_id in {None, variant_id}]
    if not batch_id and len(eligible_batches) == 1:
        batch_id = eligible_batches[0].id
    if not batch_id and len(eligible_batches) > 1:
        raise ValueError("Selecione o lote que está a ser embalado")
    available_in_revista = revista_qty(order)
    approved_total = approved_quantity(db, order, variant_id)
    from .execution import movement_holdings, record_movement
    already_packed = max(
        float(movement_holdings(db, order)["packed"]),
        float((order.custom_data or {}).get("packed_quantity") or 0),
    )
    packed_variant = sum(float(row.quantity or 0) for row in db.query(ProductionMovement).filter_by(
        production_order_id=order.id, movement_type="packing", variant_id=variant_id
    ).all()) if variant_id else already_packed
    packable = min(max(0.0, available_in_revista), max(0.0, approved_total - packed_variant))
    if quantity > packable + 0.001:
        raise ValueError(f"Só há {packable:.0f} peças aprovadas na revista por embalar")
    # Compatibilidade com OF antigas que guardavam a revista apenas no JSON.
    # Materializa esse saldo no livro antes de o consumir, preservando a
    # conservação total e evitando origens negativas.
    physical_revista = movement_holdings(db, order)["revista"]
    if available_in_revista > physical_revista + 0.001:
        record_movement(
            db, company_id=order.company_id, production_order_id=order.id,
            movement_type="distribution", quantity=available_in_revista - physical_revista,
            location_from="unassigned", location_to="revista",
            reference="Migração de saldo de revista",
            idempotency_key=f"legacy-revista:{order.id}",
        )
    data = dict(order.custom_data or {})
    data["packed_quantity"] = round(already_packed + quantity, 2)
    order.custom_data = data
    update_order_stage(db, order)
    db.flush()
    from .operations_control import create_finished_goods_unit
    unit = create_finished_goods_unit(db, order, {
        **payload, "quantity": quantity, "variant_id": variant_id, "batch_id": batch_id,
        "package_code": payload.get("package_code") or payload.get("reference"),
    }, payload.get("user_id"))
    stock = holdings(db, order)
    return {
        "order_id": order.id,
        "packed_quantity": data["packed_quantity"],
        "finished_goods_unit": {"id": unit.id, "package_code": unit.package_code, "barcode": unit.barcode, "quantity": unit.quantity},
        "holdings": {key: stock[key] for key in ("internal", "external", "shipped", "revista", "finished_goods", "unassigned", "total")},
    }


def update_order_stage(db: Session, order: ProductionOrder | None) -> str | None:
    if not order:
        return None
    new_stage = derive_stage(db, order)
    if new_stage and new_stage != order.current_stage:
        order.current_stage = new_stage
    return new_stage
