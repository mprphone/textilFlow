from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..models import (
    BOMItem, CostLine, CostSheet, Material, ProductionEvent, ProductionOrder,
    SalesOrder, StockLot, SubcontractJob, SubcontractService, User,
)
from .proposal_release import classify_cost_line, production_preview

FABRIC = {"fabric", "knit", "woven", "malha", "tecido"}
STEP_ORDER = ("dyeing", "laundry", "printing", "embroidery", "cutting", "sewing", "finishing", "transport", "other")
STEP_LABEL = {
    "dyeing": "Tinturaria", "laundry": "Lavandaria", "printing": "Estamparia", "embroidery": "Bordado",
    "cutting": "Corte", "sewing": "Confeção interna", "finishing": "Acabamento",
    "transport": "Transporte", "other": "Serviço externo",
}
GROUP_MAP = {"dyeing": "dyeing", "printing": "printing", "subcontract_other": "other"}
OPEN_JOB = {"planned", "sent", "partial", "problem"}
IDLE_DAYS = 3


def cost_sheet_for_order(db: Session, order: ProductionOrder) -> CostSheet | None:
    sheet_id = (order.custom_data or {}).get("approved_cost_sheet_id")
    if sheet_id:
        sheet = db.get(CostSheet, sheet_id)
        if sheet and sheet.company_id == order.company_id:
            return sheet
    return (
        db.query(CostSheet)
        .filter_by(company_id=order.company_id, style_id=order.style_id)
        .order_by(CostSheet.version.desc())
        .first()
    )


def snapshot_approval_needs(db: Session, sheet: CostSheet) -> dict:
    preview = production_preview(db, sheet)
    return {
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "quantity": preview["quantity"],
        "stock_summary": preview["stock_summary"],
        "requirements": [
            {
                "description": row.get("description"),
                "cost_group": row.get("cost_group"),
                "required_quantity": row.get("required_quantity"),
                "available_quantity": row.get("available_quantity"),
                "shortage_quantity": row.get("shortage_quantity"),
                "status": row.get("status"),
            }
            for row in preview["requirements"]
        ],
        "subcontracts": preview["subcontracts"],
        "warnings": preview["warnings"],
    }


def commercial_name(db: Session, order: ProductionOrder, sales: SalesOrder | None, sheet: CostSheet | None) -> str | None:
    for blob in ((order.custom_data or {}), (sales.custom_data if sales else {}) or {}, (sheet.custom_data if sheet else {}) or {}):
        name = blob.get("commercial_name")
        if name:
            return name
    meta = (sheet.custom_data if sheet else None) or {}
    user_id = meta.get("accepted_by") or meta.get("approved_by")
    if user_id:
        user = db.get(User, user_id)
        if user:
            return user.full_name
    return None


def bom_material_needs(db: Session, order: ProductionOrder) -> list[dict]:
    qty = float(order.quantity or 0)
    items = db.query(BOMItem).filter_by(company_id=order.company_id, style_id=order.style_id).order_by(BOMItem.id).all()
    material_ids = [row.material_id for row in items if row.material_id]
    lots_by_material: dict[int, list[StockLot]] = {}
    if material_ids:
        for lot in db.query(StockLot).filter(
            StockLot.company_id == order.company_id, StockLot.material_id.in_(material_ids)
        ).all():
            lots_by_material.setdefault(lot.material_id, []).append(lot)
    rows = []
    for item in items:
        material = db.get(Material, item.material_id) if item.material_id else None
        factor = 1 + ((item.waste_pct or 0) / 100)
        required = qty * (item.quantity or 0) * factor
        lots = lots_by_material.get(item.material_id or 0, [])
        available = sum(max(0.0, (lot.quantity or 0) - (lot.reserved or 0)) for lot in lots)
        reserved = sum(max(0.0, lot.reserved or 0) for lot in lots)
        shortage = max(0.0, required - available)
        category = (material.category if material else item.unit) or "other"
        group = "fabric" if str(category).lower() in FABRIC else "accessories"
        status = "shortage" if shortage > 0.001 else ("available" if available else "pending")
        rows.append({
            "id": None,
            "material_id": item.material_id,
            "description": material.name if material else "Material",
            "material_category": category,
            "cost_group": group,
            "unit": item.unit or (material.unit if material else "un"),
            "unit_required": round((item.quantity or 0) * factor, 6),
            "required_quantity": round(required, 4),
            "available_quantity": round(available, 4),
            "shortage_quantity": round(shortage, 4),
            "reserved_quantity": 0.0,
            "stock_reserved": round(reserved, 4),
            "status": status,
            "lots": [],
            "source": "bom",
        })
    return rows


def _job_category(db: Session, job: SubcontractJob) -> str:
    service = db.get(SubcontractService, job.subcontract_service_id)
    category = (service.category if service else "other") or "other"
    return category if category in STEP_ORDER else "other"


def service_plan(db: Session, order: ProductionOrder, jobs: list[SubcontractJob], internal_qty: float = 0) -> list[dict]:
    from .production_route import build_route_status, route_for_style
    if route_for_style(db, order.style_id):
        return build_route_status(db, order)
    sheet = cost_sheet_for_order(db, order)
    keys: list[str] = []
    labels: dict[str, str] = {}
    if sheet:
        for line in db.query(CostLine).filter_by(cost_sheet_id=sheet.id, category="subcontract").order_by(CostLine.id).all():
            group = GROUP_MAP.get(classify_cost_line(db, sheet, line)["cost_group"], "other")
            if group not in keys:
                keys.append(group)
                labels[group] = line.description or STEP_LABEL[group]
    if not keys:
        keys = ["dyeing", "printing"]
    if "sewing" not in keys:
        keys.append("sewing")
    jobs_by_cat: dict[str, list[SubcontractJob]] = {}
    for job in jobs:
        jobs_by_cat.setdefault(_job_category(db, job), []).append(job)

    previous_done = True
    previous_label = None
    steps = []
    for index, key in enumerate(keys, start=1):
        kind = "internal" if key == "sewing" else "external"
        related = jobs_by_cat.get(key, [])
        open_jobs = [job for job in related if job.status in OPEN_JOB]
        from .production_split import job_out
        out_qty = round(sum(job_out(job) for job in related), 2)
        complete = bool(related) and not open_jobs and all(job.status in {"received", "cancelled"} for job in related)
        locked = not previous_done
        if locked and kind == "internal" and internal_qty > 0:
            status = "in_progress"
            reason = f"Novos envios cadeados até concluir {previous_label}"
            can_go = False
        elif locked:
            status = "locked"
            reason = f"Cadeado até concluir {previous_label}"
            can_go = False
        elif open_jobs or (kind == "internal" and internal_qty > 0):
            status = "in_progress"
            reason = None
            can_go = True
        elif complete or (kind == "internal" and internal_qty >= float(order.quantity or 0) > 0):
            status = "done"
            reason = None
            can_go = False
        else:
            status = "ready"
            reason = None
            can_go = True
        label = labels.get(key) or STEP_LABEL.get(key, key)
        steps.append({
            "sequence": index,
            "key": key,
            "label": label,
            "kind": kind,
            "locked": locked,
            "status": status,
            "reason": reason,
            "out_quantity": out_qty,
            "job_count": len(related),
            "can_distribute": can_go,
        })
        previous_label = label
        previous_done = complete if kind == "external" else previous_done
    return steps


def assert_can_distribute(db: Session, order: ProductionOrder, payload: dict) -> None:
    jobs = db.query(SubcontractJob).filter_by(production_order_id=order.id).all()
    from .production_split import holdings
    stock = holdings(db, order, jobs)
    steps = service_plan(db, order, jobs, stock["internal"])
    if not steps:
        return
    destination = payload.get("destination")
    if destination == "subcontract":
        service = db.get(SubcontractService, int(payload.get("subcontract_service_id") or 0))
        if not service:
            return
        category = service.category if service.category in STEP_ORDER else "other"
        current = next((step for step in steps if step["key"] == category), None)
        if not current:
            raise ValueError("Este serviço não faz parte da sequência desta OF")
        if current["locked"]:
            raise ValueError(current["reason"] or f"{current['label']} está cadeado")
        open_other = next((step for step in steps if step["kind"] == "external" and step["status"] == "in_progress" and step["key"] != category), None)
        if open_other:
            raise ValueError(f"Ainda há {open_other['label']} a decorrer. Só se distribui um serviço de cada vez.")
        if current["status"] not in {"ready", "in_progress"}:
            raise ValueError(f"{current['label']} não está disponível para distribuição")
    elif destination == "internal":
        sewing = next((step for step in steps if step["key"] == "sewing"), None)
        if sewing and sewing["locked"]:
            raise ValueError(sewing["reason"] or "A confeção está cadeada até os serviços anteriores regressarem")


def followup_alerts(order: ProductionOrder, jobs: list[SubcontractJob], materials: list[dict], events: list, steps: list[dict], delivery: date | None, inspections: list | None = None) -> list[dict]:
    today = date.today()
    alerts = []
    for inspection in inspections or []:
        if inspection.result == "failed":
            alerts.append({
                "level": "danger",
                "title": f"Qualidade reprovada · {inspection.defect_code or inspection.inspection_type}",
                "detail": f"{inspection.defect_quantity or 0} defeito(s) em {inspection.inspected_quantity or 0} inspecionadas. Bloqueia a expedição.",
            })
    prazo = delivery or order.planned_end
    if prazo and prazo < today and order.status not in {"completed", "cancelled"}:
        alerts.append({"level": "danger", "title": "Prazo de entrega ultrapassado", "detail": f"A entrega era {prazo.isoformat()}."})
    elif prazo and (prazo - today).days <= 3 and order.status not in {"completed", "cancelled"}:
        alerts.append({"level": "warning", "title": "Entrega a 3 dias ou menos", "detail": f"Prazo {prazo.isoformat()}."})
    for job in jobs:
        if job.status == "problem":
            alerts.append({"level": "danger", "title": f"Incidência em {job.reference}", "detail": job.notes or "O subcontrato reportou um problema."})
        elif job.expected_date and job.expected_date < today and job.status in OPEN_JOB:
            alerts.append({"level": "danger", "title": f"{job.reference} parado no fornecedor", "detail": f"O regresso era {job.expected_date.isoformat()}."})
    last = events[0] if events else None
    last_time = getattr(last, "event_time", None) if last else None
    if last_time:
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        idle = (datetime.now(timezone.utc) - last_time).days
        if idle >= IDLE_DAYS and order.status in {"planned", "released", "in_progress", "paused"}:
            alerts.append({"level": "warning", "title": "Parado sem movimento", "detail": f"Último registo há {idle} dias. Verificar onde a OF está presa."})
    if any((row.get("shortage_quantity") or 0) > 0.001 for row in materials):
        missing = sum(1 for row in materials if (row.get("shortage_quantity") or 0) > 0.001)
        alerts.append({"level": "warning", "title": "Falta material para produzir", "detail": f"{missing} artigo(s) a encomendar ou a receber. Pode planear na mesma."})
    for alert in (order.custom_data or {}).get("fabric_alerts") or []:
        if alert.get("seen"):
            continue
        alerts.append({"level": alert.get("level") or "info", "title": alert.get("title") or "Malha", "detail": alert.get("detail") or ""})
    locked_ready = next((step for step in steps if step["status"] == "ready"), None)
    waiting = next((step for step in steps if step["locked"]), None)
    if locked_ready:
        alerts.append({"level": "info", "title": f"Próximo passo: {locked_ready['label']}", "detail": "Distribua só este serviço. Os seguintes ficam cadeados."})
    elif waiting:
        alerts.append({"level": "info", "title": f"Aguardar {waiting['label']}", "detail": waiting["reason"] or "Sequência de serviços em curso."})
    return alerts


def persist_service_plan(order: ProductionOrder, steps: list[dict]) -> None:
    data = dict(order.custom_data or {})
    data["service_plan"] = [{key: step[key] for key in ("sequence", "key", "label", "kind")} for step in steps]
    order.custom_data = data
