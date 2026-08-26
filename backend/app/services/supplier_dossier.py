"""Ficha de fornecedor: histórico comercial, operacional e de qualidade.

Todos os indicadores são derivados dos dados que já existem (requisições, receções,
inspeções de qualidade, encomendas e ocorrências). Nada de números introduzidos à mão.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..models import (
    Certification, CommercialDocument, ProductionOrder, PurchaseOrder, QualityInspection,
    SubcontractJob, SubcontractService, Supplier, SupplierOccurrence,
)
from .serialization import model_to_dict

KINDS = {
    "reclamacao": "Reclamação",
    "incidencia": "Incidência",
    "qualidade": "Problema de qualidade",
    "atraso": "Atraso",
    "comunicacao": "Comunicação",
    "telefonema": "Telefonema",
    "email": "Email",
    "reuniao": "Reunião",
    "nota": "Nota interna",
    "acordo": "Acordo comercial",
    "preco": "Alteração de preço",
    "outro": "Outro",
}
STATUSES = {
    "aberto": "Aberto",
    "em_analise": "Em análise",
    "aguarda_fornecedor": "A aguardar fornecedor",
    "resolvido": "Resolvido",
    "concluido": "Concluído",
    "fechado": "Fechado",
}
COMPLAINT_KINDS = {"reclamacao", "qualidade"}
OPEN_STATUSES = {"aberto", "em_analise", "aguarda_fornecedor"}
OPEN_JOB = {"planned", "sent", "partial", "problem"}
COMPLETED_JOB = {"received"}
COMPLAINT_FIELDS = (
    "motivo", "qty_affected", "qty_rejected", "cost_estimated", "cost_actual",
    "supplier_responsible", "supplier_reply", "solution", "resolved_date",
)
RATING_KEYS = ("comunicacao", "flexibilidade", "resposta", "colaboracao", "disponibilidade")
DEFAULT_WEIGHTS = {"prazo": 40, "qualidade": 30, "incidencias": 15, "preco": 15}
SUPPLIER_TYPES = {
    "material": "Materiais", "sewing": "Confeção", "dyeing": "Tinturaria", "printing": "Estamparia",
    "laundry": "Lavandaria", "transport": "Transporte", "general": "Geral", "finishing": "Acabamento",
    "embroidery": "Bordado",
}
SUPPLIER_COLUMNS = (
    "code", "name", "supplier_type", "tax_id", "email", "phone", "address", "postal_code", "city",
    "country", "fax", "contact_name", "payment_terms", "payment_term_code", "currency", "iban",
    "notes", "lead_time_days", "weekly_capacity", "piece_cost", "active",
)


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def _id(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number or None


def _days(start, end) -> int | None:
    if not start or not end:
        return None
    return (end - start).days


def _date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _period_bounds(period: str, date_from: str | None, date_to: str | None) -> tuple[date, date]:
    today = date.today()
    if period == "custom":
        start = _date(date_from) or (today - timedelta(days=365))
        end = _date(date_to) or today
        return (start, end) if start <= end else (end, start)
    if period == "year":
        return date(today.year, 1, 1), today
    months = {"3m": 3, "6m": 6, "12m": 12}.get(period, 12)
    year, month = today.year, today.month - months + 1
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1), today


def _profile(supplier: Supplier) -> dict:
    return dict(supplier.custom_data or {})


def _public_occurrence(db: Session, row: SupplierOccurrence) -> dict:
    extra = dict(row.extra or {})
    order = db.get(ProductionOrder, row.production_order_id) if row.production_order_id else None
    job = db.get(SubcontractJob, row.subcontract_job_id) if row.subcontract_job_id else None
    service = db.get(SubcontractService, row.subcontract_service_id) if row.subcontract_service_id else None
    purchase = db.get(PurchaseOrder, row.purchase_order_id) if row.purchase_order_id else None
    data = model_to_dict(row)
    data.update({
        "kind_label": KINDS.get(row.kind, row.kind),
        "status_label": STATUSES.get(row.status, row.status),
        "order_no": order.order_no if order else None,
        "job_reference": job.reference if job else None,
        "service_name": service.name if service else None,
        "purchase_no": purchase.order_no if purchase else None,
        "attachments": extra.get("attachments") or [],
        "complaint": {key: extra.get(key) for key in COMPLAINT_FIELDS} if row.kind in COMPLAINT_KINDS else None,
    })
    return data


def _score_components(metrics: dict, profile: dict) -> dict:
    weights = {**DEFAULT_WEIGHTS, **(profile.get("score_weights") or {})}
    prazo = None
    if metrics["completed"] and metrics["on_time_known"]:
        prazo = round(10 * (metrics["on_time_pct"] or 0) / 100, 1)
    qualidade = None
    if metrics["inspected"] > 0:
        qualidade = round(max(0, min(10, 10 * (1 - min(1, metrics["reject_rate"] / 0.10)))), 1)
    incidencias = round(max(0, min(10, 10 - metrics["open_complaints"] * 1.5 - metrics["incidents"] * 0.8)), 1)
    preco = None
    if metrics["price_pairs"]:
        preco = round(max(0, min(10, 10 * (1 - min(1, abs(metrics["price_deviation_pct"] / 100) / 0.15)))), 1)
    parts = {"prazo": prazo, "qualidade": qualidade, "incidencias": incidencias, "preco": preco}
    usable = {key: value for key, value in parts.items() if value is not None}
    if "prazo" not in usable and "qualidade" not in usable:
        overall = None
    else:
        total_w = sum(weights.get(key, 0) for key in usable) or 1
        overall = round(sum(usable[key] * weights.get(key, 0) for key in usable) / total_w, 1)
    return {"overall": overall, "parts": parts, "weights": weights}


def _job_metrics(jobs: list[SubcontractJob], start: date, end: date) -> dict:
    in_period = []
    open_jobs = []
    for job in jobs:
        if job.status in OPEN_JOB and job.status != "cancelled":
            open_jobs.append(job)
        marker = job.received_date or job.sent_date or job.expected_date
        if marker and start <= marker <= end:
            in_period.append(job)
    completed = [job for job in in_period if job.status in COMPLETED_JOB and job.received_date]
    on_time = late = 0
    real_leads, planned_leads, delays = [], [], []
    accepted = rejected = 0.0
    planned_cost = actual_cost = 0.0
    price_pairs = 0
    monthly: dict[str, dict] = {}
    for job in completed:
        planned = _days(job.sent_date, job.expected_date)
        real = _days(job.sent_date, job.received_date)
        delay = _days(job.expected_date, job.received_date)
        if planned is not None:
            planned_leads.append(planned)
        if real is not None:
            real_leads.append(real)
        if delay is not None:
            delays.append(delay)
            if delay <= 0:
                on_time += 1
            else:
                late += 1
        accepted += job.accepted_quantity or 0
        rejected += job.rejected_quantity or 0
        if (job.planned_cost or 0) > 0 and (job.actual_cost or 0) > 0:
            planned_cost += job.planned_cost
            actual_cost += job.actual_cost
            price_pairs += 1
        if job.received_date:
            bucket = monthly.setdefault(job.received_date.strftime("%Y-%m"), {"on_time": 0, "late": 0})
            if delay is None:
                continue
            if delay <= 0:
                bucket["on_time"] += 1
            else:
                bucket["late"] += 1
    known = on_time + late
    inspected = accepted + rejected
    last_three = sorted(completed, key=lambda row: row.received_date or date.min)[-3:]
    consecutive_late = 0
    for job in reversed(last_three):
        delay = _days(job.expected_date, job.received_date)
        if delay is not None and delay > 0:
            consecutive_late += 1
        else:
            break
    return {
        "open_jobs": open_jobs,
        "completed": len(completed),
        "on_time": on_time,
        "late": late,
        "on_time_known": known,
        "on_time_pct": round(100 * on_time / known, 1) if known else None,
        "avg_planned": round(sum(planned_leads) / len(planned_leads), 1) if planned_leads else None,
        "avg_real": round(sum(real_leads) / len(real_leads), 1) if real_leads else None,
        "avg_delay": round(sum(delays) / len(delays), 1) if delays else None,
        "inspected": inspected,
        "rejected": rejected,
        "reject_rate": (rejected / inspected) if inspected else 0,
        "price_pairs": price_pairs,
        "price_deviation_pct": round(100 * (actual_cost - planned_cost) / planned_cost, 1) if planned_cost else 0,
        "spend_jobs": round(sum((job.actual_cost or job.planned_cost or 0) for job in in_period), 2),
        "monthly": monthly,
        "consecutive_late": consecutive_late,
        "completed_rows": completed,
        "period_jobs": in_period,
    }


def _alerts(metrics: dict, occurrences: list[dict], certs: list[dict], profile: dict) -> list[dict]:
    alerts: list[dict] = []
    today = date.today()
    for row in occurrences:
        if row["kind"] in COMPLAINT_KINDS and row["status"] in OPEN_STATUSES:
            occurred = _date(row.get("occurred_on"))
            age = (today - occurred).days if occurred else 0
            if age >= 5:
                alerts.append({
                    "level": "danger", "title": "Reclamação aberta há mais de 5 dias",
                    "detail": f"{row['subject']} · {age} dias", "tab": "ocorrencias",
                })
    if metrics["consecutive_late"] >= 3:
        alerts.append({
            "level": "warn", "title": "Três entregas consecutivas atrasadas",
            "detail": "O fornecedor está a falhar o prazo nas últimas receções.", "tab": "desempenho",
        })
    if metrics["on_time_pct"] is not None and metrics["on_time_pct"] < 80 and metrics["on_time_known"] >= 3:
        alerts.append({
            "level": "warn", "title": "Cumprimento de prazo abaixo de 80%",
            "detail": f"{metrics['on_time_pct']}% no período.", "tab": "desempenho",
        })
    limit = float(profile.get("rejection_limit_pct") or 5)
    if metrics["inspected"] and metrics["reject_rate"] * 100 > limit:
        alerts.append({
            "level": "danger", "title": "Taxa de rejeição acima do limite",
            "detail": f"{round(metrics['reject_rate'] * 100, 1)}% (limite {limit}%).", "tab": "desempenho",
        })
    for cert in certs:
        expiry = _date(cert.get("expiry_date"))
        if not expiry:
            continue
        left = (expiry - today).days
        if 0 <= left <= 45:
            alerts.append({
                "level": "info", "title": "Certificação a expirar",
                "detail": f"{cert.get('cert_type')} · {left} dias", "tab": "documentos",
            })
    return alerts


def _evolution(monthly: dict, start: date, end: date) -> list[dict]:
    cursor = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    rows = []
    while cursor <= last:
        bucket = monthly.get(cursor.strftime("%Y-%m")) or {"on_time": 0, "late": 0}
        total = bucket["on_time"] + bucket["late"]
        rows.append({
            "month": cursor.strftime("%Y-%m"),
            "label": cursor.strftime("%m/%Y"),
            "on_time": bucket["on_time"],
            "late": bucket["late"],
            "pct": round(100 * bucket["on_time"] / total, 1) if total else None,
        })
        year, month = (cursor.year + 1, 1) if cursor.month == 12 else (cursor.year, cursor.month + 1)
        cursor = date(year, month, 1)
    return rows


def _supplier_card(supplier: Supplier, profile: dict) -> dict:
    data = model_to_dict(supplier)
    data.pop("custom_data", None)
    data["type_label"] = SUPPLIER_TYPES.get(supplier.supplier_type, supplier.supplier_type)
    data["profile"] = profile
    return data


def _load_supplier(db: Session, company_id: int, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if not supplier or supplier.company_id != company_id:
        raise HTTPException(404, "Fornecedor não encontrado")
    return supplier


def supplier_dossier(db: Session, company_id: int, supplier_id: int, period: str = "12m",
                     date_from: str | None = None, date_to: str | None = None) -> dict:
    supplier = _load_supplier(db, company_id, supplier_id)
    start, end = _period_bounds(period, date_from, date_to)
    profile = _profile(supplier)

    jobs = db.query(SubcontractJob).filter_by(company_id=company_id, supplier_id=supplier_id).all()
    services = db.query(SubcontractService).filter_by(company_id=company_id, supplier_id=supplier_id).order_by(SubcontractService.name).all()
    purchases = db.query(PurchaseOrder).filter_by(company_id=company_id, supplier_id=supplier_id).order_by(PurchaseOrder.order_date.desc()).all()
    documents = db.query(CommercialDocument).filter_by(company_id=company_id, supplier_id=supplier_id).order_by(CommercialDocument.doc_date.desc()).all()
    inspections = db.query(QualityInspection).filter_by(company_id=company_id, supplier_id=supplier_id).all()
    certs = db.query(Certification).filter_by(company_id=company_id, supplier_id=supplier_id).all()
    occurrences = [
        _public_occurrence(db, row)
        for row in db.query(SupplierOccurrence).filter_by(company_id=company_id, supplier_id=supplier_id)
        .order_by(SupplierOccurrence.occurred_on.desc(), SupplierOccurrence.id.desc()).all()
    ]

    metrics = _job_metrics(jobs, start, end)
    if inspections:
        inspected = sum(row.inspected_quantity or 0 for row in inspections)
        defects = sum(row.defect_quantity or 0 for row in inspections)
        if inspected:
            metrics["inspected"] = inspected
            metrics["rejected"] = defects
            metrics["reject_rate"] = defects / inspected
    metrics["incidents"] = sum(1 for row in occurrences if row["kind"] in {"incidencia", "atraso", "qualidade", "reclamacao"})
    metrics["open_complaints"] = sum(1 for row in occurrences if row["kind"] in COMPLAINT_KINDS and row["status"] in OPEN_STATUSES)
    score = _score_components(metrics, profile)

    last_buy = next((row for row in purchases if row.order_date), None)
    last_job = max((job for job in jobs if job.sent_date or job.received_date),
                   key=lambda row: row.received_date or row.sent_date, default=None)
    last_purchase_date = last_purchase_ref = None
    if last_buy and last_job:
        job_date = last_job.received_date or last_job.sent_date
        if job_date and (not last_buy.order_date or job_date >= last_buy.order_date):
            last_purchase_date, last_purchase_ref = job_date, last_job.reference
        else:
            last_purchase_date, last_purchase_ref = last_buy.order_date, last_buy.order_no
    elif last_buy:
        last_purchase_date, last_purchase_ref = last_buy.order_date, last_buy.order_no
    elif last_job:
        last_purchase_date, last_purchase_ref = last_job.received_date or last_job.sent_date, last_job.reference

    period_purchases = [row for row in purchases if row.order_date and start <= row.order_date <= end]
    period_docs = [row for row in documents if row.doc_date and start <= row.doc_date <= end]
    spend = metrics["spend_jobs"] + sum(row.total or 0 for row in period_purchases) + sum(
        row.total or 0 for row in period_docs if row.doc_type in {"purchase_invoice", "requisition"}
    )
    year_start = date(date.today().year, 1, 1)
    year_spend = sum((job.actual_cost or job.planned_cost or 0) for job in jobs
                     if (job.received_date or job.sent_date or date.min) >= year_start)
    year_spend += sum(row.total or 0 for row in purchases if row.order_date and row.order_date >= year_start)

    cert_rows = [model_to_dict(row) for row in certs]
    order_ids = {job.production_order_id for job in jobs if job.production_order_id}
    orders = {row.id: row for row in db.query(ProductionOrder).filter(ProductionOrder.id.in_(order_ids)).all()} if order_ids else {}

    def job_row(job: SubcontractJob) -> dict:
        order = orders.get(job.production_order_id)
        service = next((row for row in services if row.id == job.subcontract_service_id), None)
        return {
            **model_to_dict(job),
            "order_no": order.order_no if order else None,
            "service_name": service.name if service else None,
            "planned_days": _days(job.sent_date, job.expected_date),
            "real_days": _days(job.sent_date, job.received_date),
            "delay_days": _days(job.expected_date, job.received_date),
        }

    alerts = _alerts(metrics, occurrences, cert_rows, profile)
    ratings = {key: value for key, value in (profile.get("internal_ratings") or {}).items() if key in RATING_KEYS}
    stars = round((score["overall"] or 0) / 2, 1) if score["overall"] is not None else None
    return {
        "supplier": _supplier_card(supplier, profile),
        "period": {"id": period, "start": start.isoformat(), "end": end.isoformat()},
        "summary": {
            "score": score["overall"],
            "stars": stars,
            "on_time_pct": metrics["on_time_pct"],
            "avg_real": metrics["avg_real"],
            "open_complaints": metrics["open_complaints"],
            "last_occurrence": occurrences[0]["occurred_on"] if occurrences else None,
            "last_purchase": _iso(last_purchase_date),
            "last_purchase_ref": last_purchase_ref,
            "open_jobs": len(metrics["open_jobs"]),
        },
        "performance": {
            "completed": metrics["completed"],
            "on_time": metrics["on_time"],
            "late": metrics["late"],
            "on_time_pct": metrics["on_time_pct"],
            "avg_planned": metrics["avg_planned"],
            "avg_real": metrics["avg_real"],
            "avg_delay": metrics["avg_delay"],
            "incidents": metrics["incidents"],
            "complaints": metrics["open_complaints"],
            "reject_rate_pct": round(metrics["reject_rate"] * 100, 1) if metrics["inspected"] else None,
            "evolution": _evolution(metrics["monthly"], start, end),
        },
        "score": score,
        "finance": {
            "period_spend": round(spend, 2),
            "year_spend": round(year_spend, 2),
            "requisitions": len(metrics["period_jobs"]),
            "price_deviation_pct": metrics["price_deviation_pct"] if metrics["price_pairs"] else None,
        },
        "internal_ratings": ratings,
        "alerts": alerts,
        "services": [model_to_dict(row) for row in services],
        "open_jobs": [job_row(job) for job in sorted(metrics["open_jobs"], key=lambda row: row.sent_date or date.min, reverse=True)],
        "history": [job_row(job) for job in sorted(metrics["period_jobs"], key=lambda row: row.received_date or row.sent_date or date.min, reverse=True)],
        "purchases": [model_to_dict(row) for row in purchases[:40]],
        "documents": [model_to_dict(row) for row in documents[:40]],
        "certifications": cert_rows,
        "occurrences": occurrences,
        "recent_occurrences": occurrences[:5],
        "kinds": KINDS,
        "statuses": STATUSES,
    }


def _bind_occurrence_links(db: Session, company_id: int, supplier_id: int, payload: dict, row) -> None:
    checks = (
        ("production_order_id", ProductionOrder, None),
        ("subcontract_job_id", SubcontractJob, "supplier_id"),
        ("subcontract_service_id", SubcontractService, "supplier_id"),
        ("purchase_order_id", PurchaseOrder, "supplier_id"),
    )
    for field, model, supplier_attr in checks:
        if field not in payload:
            continue
        ident = _id(payload.get(field))
        if not ident:
            setattr(row, field, None)
            continue
        entity = db.get(model, ident)
        if not entity or getattr(entity, "company_id", None) != company_id:
            raise HTTPException(422, "O documento ligado não pertence a esta empresa")
        if supplier_attr and getattr(entity, supplier_attr, None) != supplier_id:
            raise HTTPException(422, "O documento ligado não pertence a este fornecedor")
        setattr(row, field, ident)


def upsert_occurrence(db: Session, company_id: int, supplier_id: int, payload: dict,
                      occurrence_id: int | None = None) -> dict:
    _load_supplier(db, company_id, supplier_id)
    if occurrence_id:
        row = db.get(SupplierOccurrence, occurrence_id)
        if not row or row.company_id != company_id or row.supplier_id != supplier_id:
            raise HTTPException(404, "Ocorrência não encontrada")
    else:
        row = SupplierOccurrence(company_id=company_id, supplier_id=supplier_id)
        db.add(row)

    if "occurred_on" in payload or not occurrence_id:
        occurred = _date(payload.get("occurred_on")) or date.today()
        row.occurred_on = occurred
    kind = str(payload.get("kind") or row.kind or "comunicacao").strip().lower()
    if kind not in KINDS:
        raise HTTPException(422, "Tipo de ocorrência inválido")
    row.kind = kind
    subject = str(payload.get("subject") or row.subject or "").strip()
    if not subject:
        raise HTTPException(422, "Indique o assunto da ocorrência")
    row.subject = subject[:250]
    status = str(payload.get("status") or row.status or "aberto").strip().lower()
    if status not in STATUSES:
        raise HTTPException(422, "Estado da ocorrência inválido")
    row.status = status
    if "description" in payload:
        row.description = payload.get("description") or None
    if "responsible" in payload:
        row.responsible = (payload.get("responsible") or None)
    if "priority" in payload:
        row.priority = str(payload.get("priority") or "normal").strip().lower()
    if "due_date" in payload:
        row.due_date = _date(payload.get("due_date"))
    _bind_occurrence_links(db, company_id, supplier_id, payload, row)

    extra = dict(row.extra or {})
    if "attachments" in payload:
        extra["attachments"] = payload.get("attachments") or []
    if kind in COMPLAINT_KINDS:
        for field in COMPLAINT_FIELDS:
            if field not in payload:
                continue
            value = payload.get(field)
            extra[field] = None if value in ("", None) else value
    row.extra = extra
    db.flush()
    if occurrence_id:
        flag_modified(row, "extra")
    db.commit()
    db.refresh(row)
    return _public_occurrence(db, row)


def delete_occurrence(db: Session, company_id: int, supplier_id: int, occurrence_id: int) -> None:
    row = db.get(SupplierOccurrence, occurrence_id)
    if not row or row.company_id != company_id or row.supplier_id != supplier_id:
        raise HTTPException(404, "Ocorrência não encontrada")
    db.delete(row)
    db.commit()


def list_order_occurrences(db: Session, company_id: int, order_id: int) -> list[dict]:
    rows = db.query(SupplierOccurrence).filter_by(company_id=company_id, production_order_id=order_id) \
        .order_by(SupplierOccurrence.occurred_on.desc(), SupplierOccurrence.id.desc()).all()
    suppliers = {row.id: row.name for row in db.query(Supplier).filter_by(company_id=company_id).all()}
    items = []
    for row in rows:
        data = _public_occurrence(db, row)
        data["supplier_name"] = suppliers.get(row.supplier_id)
        items.append(data)
    return items


def save_profile(db: Session, company_id: int, supplier_id: int, payload: dict) -> dict:
    supplier = _load_supplier(db, company_id, supplier_id)
    profile = _profile(supplier)
    for key in SUPPLIER_COLUMNS:
        if key not in payload:
            continue
        value = payload.get(key)
        if key == "active":
            supplier.active = bool(value)
        elif key in ("lead_time_days",):
            supplier.lead_time_days = int(value or 0)
        elif key in ("weekly_capacity", "piece_cost"):
            setattr(supplier, key, float(value or 0))
        else:
            setattr(supplier, key, None if value == "" else value)
    if "internal_ratings" in payload:
        ratings = payload.get("internal_ratings") or {}
        profile["internal_ratings"] = {
            key: max(0, min(5, int(ratings.get(key) or 0)))
            for key in RATING_KEYS if key in ratings
        }
    for key, value in (payload or {}).items():
        if key in SUPPLIER_COLUMNS or key in ("internal_ratings", "company_id", "id"):
            continue
        profile[key] = value
    supplier.custom_data = profile
    flag_modified(supplier, "custom_data")
    db.commit()
    db.refresh(supplier)
    return _supplier_card(supplier, _profile(supplier))
