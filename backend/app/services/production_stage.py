from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import CuttingJob, ProductionBatch, ProductionOrder, QualityInspection, SalesOrderLine, SewingPlan, Shipment, SubcontractJob
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
    job = (
        db.query(CuttingJob)
        .filter_by(company_id=order.company_id, production_order_id=order.id)
        .order_by(CuttingJob.id.desc())
        .first()
    )
    if not job:
        return "not_started", None
    if job.status in {"completed", "done"} or float(job.good_pieces or 0) >= float(order.quantity or 0) * 0.99:
        return "completed", job
    if float(job.actual_fabric or 0) > 0.001 or float(job.good_pieces or 0) > 0.001:
        return "in_progress", job
    return "planned", job


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
    return [job.status for job in open_jobs]


def derive_stage(db: Session, order: ProductionOrder) -> str:
    if order.status in {"completed", "cancelled"}:
        return order.status
    if order.completed_quantity and float(order.completed_quantity or 0) >= float(order.quantity or 0) * 0.99:
        return "completed"

    has_fabric = _has_fabric_requirement(db, order)
    fabric_status_result = fabric_status(db, order)
    cutting_state, _job = _cutting_state(db, order)
    sewing_state, _sewing_qty = _sewing_state(db, order)

    # Se já está em expedição, mantém até concluir
    data = order.custom_data or {}
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
    existing = db.query(ProductionBatch).filter_by(company_id=order.company_id, production_order_id=order.id).count()
    if existing:
        return []
    pieces = int(job.good_pieces or 0)
    if pieces <= 0:
        return []
    batch = ProductionBatch(
        company_id=order.company_id,
        production_order_id=order.id,
        batch_no=f"{order.order_no}-CORTE",
        color=job.fabric_lot or "",
        quantity=pieces,
        completed_quantity=0,
        current_location="Corte",
        status="waiting",
        kanban_status=KANBAN_WAITING,
    )
    db.add(batch)
    db.flush()
    if not db.query(QualityInspection).filter_by(company_id=order.company_id, production_order_id=order.id, inspection_type="incoming_cut").first():
        inspection = QualityInspection(
            company_id=order.company_id,
            production_order_id=order.id,
            batch_id=batch.id,
            inspection_type="incoming_cut",
            inspected_quantity=pieces,
            result="pending",
            notes="Corte concluído · aguarda inspeção de entrada.",
        )
        db.add(inspection)
    return [batch]


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
    if not sales_order:
        return {"ready": False, "reason": "Encomenda não encontrada", "missing": []}
    lines = db.query(SalesOrderLine).filter_by(sales_order_id=sales_order.id).all()
    missing = []
    for line in lines:
        # A ligacao e inversa: e a OF que aponta para a linha, nao o contrario.
        orders = db.query(ProductionOrder).filter_by(sales_order_line_id=line.id).all()
        if not orders:
            missing.append(f"Linha {line.id}: sem OF associada")
            continue
        produced = sum(float(order.completed_quantity or 0) for order in orders)
        needed = float(line.quantity or 0)
        if produced + 0.001 < needed:
            order_names = ", ".join(order.order_no for order in orders)
            missing.append(f"OF {order_names}: só produziu {produced} de {needed}")
        for order in orders:
            open_jobs = db.query(SubcontractJob).filter_by(production_order_id=order.id).filter(SubcontractJob.status.in_({"planned", "sent", "partial", "in_progress", "problem"})).count()
            if open_jobs:
                missing.append(f"OF {order.order_no}: {open_jobs} subcontrato(s) ainda não regressou")
            inspections = db.query(QualityInspection).filter_by(production_order_id=order.id).all()
            failed = [row for row in inspections if row.result == "failed" or (row.defect_quantity or 0) > (row.inspected_quantity or 0) - (row.defect_quantity or 0)]
            if failed:
                missing.append(f"OF {order.order_no}: qualidade com {len(failed)} inspeção/ões reprovada(s)")
    return {"ready": not missing, "reason": "; ".join(missing) if missing else "Pronta para expedição", "missing": missing}


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
    update_order_stage(db, order)
    return inspection


def record_packing(db: Session, order: ProductionOrder, payload: dict) -> dict:
    """Regista peças embaladas — informativo (para o stock de produto acabado);
    a saída real da fábrica continua a ser o /distribute para "shipped"."""
    from .production_split import holdings, revista_qty
    quantity = float(payload.get("quantity") or 0)
    if quantity <= 0.001:
        raise ValueError("Indique a quantidade embalada")
    available = revista_qty(order)
    already_packed = float((order.custom_data or {}).get("packed_quantity") or 0)
    if quantity > max(0.0, available - already_packed) + 0.001:
        raise ValueError(f"Só há {max(0.0, available - already_packed):.0f} pecas na revista por embalar")
    data = dict(order.custom_data or {})
    data["packed_quantity"] = round(already_packed + quantity, 2)
    order.custom_data = data
    update_order_stage(db, order)
    db.flush()
    stock = holdings(db, order)
    return {
        "order_id": order.id,
        "packed_quantity": data["packed_quantity"],
        "holdings": {key: stock[key] for key in ("internal", "external", "shipped", "revista", "unassigned", "total")},
    }


def update_order_stage(db: Session, order: ProductionOrder | None) -> str | None:
    if not order:
        return None
    new_stage = derive_stage(db, order)
    if new_stage and new_stage != order.current_stage:
        order.current_stage = new_stage
    return new_stage
