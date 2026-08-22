from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import (
    CuttingJob, Department, Employee, Machine, ProcessJob, ProductionLine,
    ProductionOrder, Style, SubcontractJob, SubcontractService,
)
from .modules import PLANT_CATALOG
from .production_split import job_out
from .serialization import model_to_dict

OPEN_JOB = {"planned", "in_progress", "paused"}


def plant_of(kind: str) -> dict:
    for module_id, item in PLANT_CATALOG.items():
        if module_id == kind or item["kind"] == kind:
            return {"id": module_id, **item}
    raise ValueError("Processo desconhecido")


def _matches_tokens(text: str, tokens: tuple[str, ...]) -> bool:
    haystack = (text or "").lower()
    return any(token in haystack for token in tokens)


def process_cockpit(db: Session, company_id: int, kind: str) -> dict:
    plant = plant_of(kind)
    process_kind = plant["kind"]
    tokens = plant["tokens"]
    jobs = (
        db.query(ProcessJob)
        .filter_by(company_id=company_id, process_kind=process_kind)
        .order_by(ProcessJob.id.desc())
        .limit(80)
        .all()
    )
    open_jobs = [job for job in jobs if job.status in OPEN_JOB]
    orders = db.query(ProductionOrder).filter(
        ProductionOrder.company_id == company_id,
        ProductionOrder.status.notin_(["completed", "cancelled"]),
        or_(
            ProductionOrder.current_stage.ilike(f"%{process_kind}%"),
            ProductionOrder.current_stage.ilike(f"%{plant['label']}%"),
        ),
    ).all()
    services = {row.id: row for row in db.query(SubcontractService).filter_by(company_id=company_id).all()}
    outside = []
    for job in db.query(SubcontractJob).filter_by(company_id=company_id).all():
        service = services.get(job.subcontract_service_id)
        category = (service.category if service else "") or ""
        if category == process_kind or _matches_tokens(service.name if service else "", tokens):
            qty = job_out(job)
            if qty > 0 or job.status in {"planned", "sent", "partial", "problem"}:
                outside.append({**model_to_dict(job), "out_quantity": qty, "service_name": service.name if service else None})
    departments = db.query(Department).filter_by(company_id=company_id).all()
    dept_ids = [row.id for row in departments if _matches_tokens(f"{row.code} {row.name}", tokens)]
    machines = db.query(Machine).filter_by(company_id=company_id).all()
    people = db.query(Employee).filter_by(company_id=company_id).all()
    lines = db.query(ProductionLine).filter_by(company_id=company_id).all()
    if dept_ids:
        machines = [row for row in machines if row.department_id in dept_ids]
        people = [row for row in people if row.department_id in dept_ids]
        lines = [row for row in lines if row.department_id in dept_ids]
    else:
        machines, people, lines = [], [], []
    styles = {row.id: row for row in db.query(Style).filter_by(company_id=company_id).all()}
    order_rows = []
    for order in orders:
        style = styles.get(order.style_id)
        order_rows.append({
            **model_to_dict(order),
            "reference": style.reference if style else "",
            "description": style.description if style else "",
        })
    cutting = []
    if process_kind == "cutting":
        cutting = [model_to_dict(row) for row in db.query(CuttingJob).filter_by(company_id=company_id).order_by(CuttingJob.id.desc()).limit(40).all()]
    today = date.today().isoformat()
    return {
        "plant": {**plant, "id": plant["id"]},
        "counts": {
            "open_jobs": len(open_jobs),
            "orders": len(order_rows),
            "outside": len(outside),
            "machines": len(machines),
            "people": len(people),
            "lines": len(lines),
        },
        "jobs": [model_to_dict(row) for row in jobs],
        "orders": order_rows,
        "outside": outside,
        "machines": [{"id": row.id, "code": row.code, "name": row.name, "status": getattr(row, "status", None)} for row in machines[:40]],
        "people": [{"id": row.id, "code": row.code, "name": row.name, "job_title": row.job_title} for row in people[:40]],
        "lines": [{"id": row.id, "code": row.code, "name": row.name} for row in lines],
        "cutting": cutting,
        "today": today,
    }
