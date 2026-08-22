from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session, joinedload, selectinload

from ..models import Customer, ProductionOrder, Sample, Style, User, UserCompany
from ..models.development import (
    Development, DevelopmentAssignee, DevelopmentComment, DevelopmentStageEvent, DevelopmentTask,
)
from .design_pipeline import (
    ACTIVE, ASSIGNEE_ROLES, BLOCKED, CLOSED_STATUSES, COMPLETED, PHASE_TWO, REJECTED, STAGE_IDS,
    TASK_KINDS, TASK_STATUSES, WAITING_CLIENT, WAITING_STATUSES, WAITING_SUPPLIER,
    DesignError, as_aware, average_stage_durations, build_suggestions, days_in_current_stage,
    estimate_completion, get_next_action, is_archived, priority_score,
    risk_from_suggestions, utcnow,
)

PATCHABLE = {
    "status", "waiting_reason", "description", "due_date", "estimated_value", "production_quantity",
    "owner_name", "cover_url", "images", "request_source", "request_group", "requested_quantity",
    "request_notes", "title",
}
STATUS_HISTORY = {
    WAITING_SUPPLIER: "aguardava fornecedor",
    WAITING_CLIENT: "aguardava cliente",
    BLOCKED: "estava bloqueado",
}


def _load_options():
    return (
        joinedload(Development.customer),
        selectinload(Development.tasks).joinedload(DevelopmentTask.responsible),
        selectinload(Development.assignees).joinedload(DevelopmentAssignee.user),
        selectinload(Development.comments),
        selectinload(Development.stage_events).joinedload(DevelopmentStageEvent.supplier),
        joinedload(Development.style),
        joinedload(Development.production_order),
    )


def get_development(db: Session, company_id: int, development_id: int) -> Development:
    item = (
        db.query(Development)
        .options(*_load_options())
        .filter_by(id=development_id, company_id=company_id)
        .first()
    )
    if not item:
        raise DesignError("Desenvolvimento não encontrado", 404)
    return item


def list_developments(db: Session, company_id: int) -> list[Development]:
    return (
        db.query(Development)
        .options(*_load_options())
        .filter_by(company_id=company_id)
        .order_by(Development.updated_at.desc(), Development.id.desc())
        .all()
    )


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def initials_for(users: list[User]) -> str:
    chosen = [user for user in users if user]
    if not chosen:
        return ""
    if len(chosen) == 1:
        parts = [part for part in (chosen[0].full_name or "").split() if part]
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[-1][0]}".upper()
        return (chosen[0].full_name or "XX")[:2].upper()
    return "".join((user.full_name or " ").strip()[:1].upper() for user in chosen)


def owner_name_for(users: list[User]) -> str:
    names = [user.full_name for user in users if user and user.full_name]
    return " + ".join(names) if names else "Por distribuir"


def next_reference(db: Session, company_id: int, customer_id: int, user_ids: list[int] | None = None) -> dict:
    customer = db.get(Customer, customer_id)
    if not customer or customer.company_id != company_id:
        raise DesignError("Cliente não encontrado", 404)
    code = (customer.code or "").strip().upper()
    if not code:
        raise DesignError("Este cliente ainda não tem código de referência. Defina-o na ficha do cliente.")
    users = []
    for user_id in user_ids or []:
        user = db.get(User, user_id)
        if user:
            users.append(user)
    initials = initials_for(users)
    pattern = re.compile(rf"_{re.escape(code)}_(\d+)")
    rows = [row[0] for row in db.query(Development.code).filter_by(company_id=company_id).all() if row[0]]
    rows += [row[0] for row in db.query(Style.reference).filter_by(company_id=company_id).all() if row[0]]
    sequences = [int(match.group(1)) for row in rows if (match := pattern.search(row.upper()))]
    nxt = (max(sequences) + 1) if sequences else 1
    seq = f"{nxt:03d}"
    reference = f"{initials}_{code}_{seq}" if initials else f"{code}_{seq}"
    return {"reference": reference, "sequence": nxt, "client_code": code, "initials": initials}


def serialize_development(development: Development, averages: dict | None = None) -> dict:
    suggestions = build_suggestions(development)
    images = list(development.images or [])
    if development.cover_url and development.cover_url not in images:
        images.insert(0, development.cover_url)
    tasks = sorted(development.tasks or [], key=lambda task: (task.status == "done", task.id or 0))
    return {
        "id": development.id,
        "company_id": development.company_id,
        "customer_id": development.customer_id,
        "customer_name": development.customer.name if development.customer else "",
        "customer_code": development.customer.code if development.customer else "",
        "style_id": development.style_id,
        "sample_id": development.sample_id,
        "production_order_id": development.production_order_id,
        "code": development.code,
        "title": development.title,
        "owner_name": development.owner_name,
        "cover_url": development.cover_url,
        "images": images,
        "request_source": development.request_source,
        "request_group": development.request_group,
        "requested_quantity": development.requested_quantity,
        "request_notes": development.request_notes,
        "current_stage": development.current_stage,
        "status": development.status,
        "waiting_reason": development.waiting_reason,
        "description": development.description,
        "due_date": _iso(development.due_date),
        "estimated_value": development.estimated_value,
        "production_quantity": development.production_quantity,
        "created_at": _iso(development.created_at),
        "updated_at": _iso(development.updated_at),
        "days_in_stage": days_in_current_stage(development),
        "next_action": get_next_action(development),
        "risk": risk_from_suggestions(suggestions),
        "suggestions": suggestions,
        "archived": is_archived(development),
        "comments_count": len(development.comments or []),
        "open_tasks_count": sum(1 for task in tasks if task.status not in {"done", "cancelled"}),
        "assignees": [
            {"id": item.id, "user_id": item.user_id, "name": item.user.full_name if item.user else "", "role": item.role}
            for item in development.assignees or []
        ],
        "tasks": [
            {
                "id": task.id, "kind": task.kind, "status": task.status, "note": task.note,
                "due_date": _iso(task.due_date), "responsible_user_id": task.responsible_user_id,
                "responsible_name": task.responsible.full_name if task.responsible else None,
                "completed_at": _iso(task.completed_at),
            }
            for task in tasks
        ],
        "estimated_completion": _iso(estimate_completion(development, averages or {})),
    }


def serialize_detail(db: Session, development: Development) -> dict:
    averages = average_stage_durations(
        db.query(DevelopmentStageEvent)
        .join(Development, Development.id == DevelopmentStageEvent.development_id)
        .filter(Development.company_id == development.company_id)
        .all()
    )
    data = serialize_development(development, averages)
    history = []
    for event in sorted(development.stage_events or [], key=lambda item: item.started_at or utcnow()):
        started = event.started_at
        ended = event.ended_at or utcnow()
        seconds = (as_aware(ended) - as_aware(started)).total_seconds() if started else 0
        history.append({
            "id": event.id,
            "stage": event.stage,
            "status": event.status,
            "started_at": _iso(event.started_at),
            "ended_at": _iso(event.ended_at),
            "days": round(seconds / 86400, 1),
            "note": event.note,
            "responsible_name": event.responsible_name,
            "supplier_name": event.supplier.name if event.supplier else None,
        })
    eta = estimate_completion(development, averages)
    data["stage_history"] = history
    data["estimated_completion"] = _iso(eta)
    data["eta_at_risk"] = bool(eta and development.due_date and eta > development.due_date)
    data["comments"] = [
        {"id": item.id, "author": item.author, "body": item.body, "category": item.category, "created_at": _iso(item.created_at)}
        for item in sorted(development.comments or [], key=lambda item: item.created_at or utcnow(), reverse=True)
    ]
    if development.production_order:
        order = development.production_order
        data["production"] = {
            "id": order.id, "order_no": order.order_no, "quantity": order.quantity,
            "status": order.status, "planned_end": _iso(order.planned_end),
        }
    else:
        data["production"] = None
    data["style"] = None
    if development.style:
        data["style"] = {
            "id": development.style.id, "reference": development.style.reference,
            "description": development.style.description, "lifecycle_status": development.style.lifecycle_status,
        }
    return data


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def _sync_style(style: Style, development: Development) -> None:
    style.customer_id = development.customer_id
    style.description = development.title
    style.workflow_stage = development.current_stage
    if development.cover_url:
        style.image_url = development.cover_url
    if development.status == REJECTED or development.status == "cancelled":
        style.lifecycle_status = "inactive"
        style.workflow_stage = "arquivado"
        style.approved = False
    elif development.current_stage == "aprovado":
        style.lifecycle_status = "approved"
        style.approved = True
        style.approved_at = utcnow()
    else:
        style.lifecycle_status = "development"
        style.approved = False


def ensure_style(db: Session, development: Development) -> Style:
    if development.style_id:
        style = db.get(Style, development.style_id)
        if style:
            _sync_style(style, development)
            return style
    existing = db.query(Style).filter_by(company_id=development.company_id, reference=development.code).first()
    if existing:
        development.style_id = existing.id
        _sync_style(existing, development)
        return existing
    style = Style(
        company_id=development.company_id,
        customer_id=development.customer_id,
        reference=development.code,
        description=development.title,
        lifecycle_status="development",
        workflow_stage=development.current_stage,
        image_url=development.cover_url,
        custom_data={"source": "design_pipeline", "development_id": development.id},
    )
    db.add(style)
    db.flush()
    development.style_id = style.id
    return style


def _add_stage_event(db: Session, development: Development, stage: str, note: str | None = None, responsible_name: str | None = None, status: str = "active"):
    db.add(DevelopmentStageEvent(
        development_id=development.id,
        stage=stage,
        status=status,
        started_at=utcnow() if status == "active" else utcnow(),
        ended_at=None,
        note=note,
        responsible_name=responsible_name or development.owner_name,
    ))


def create_developments(db: Session, company_id: int, payload: dict) -> list[Development]:
    customer_id = int(payload.get("customer_id") or 0)
    customer = db.get(Customer, customer_id)
    if not customer or customer.company_id != company_id:
        raise DesignError("Escolha um cliente válido.")
    models = payload.get("models") or []
    if not models:
        models = [{
            "title": payload.get("title"),
            "code": payload.get("code"),
            "user_ids": payload.get("user_ids") or [],
            "quantity": payload.get("requested_quantity"),
            "cover_url": payload.get("cover_url"),
        }]
    created = []
    due_date = _parse_date(payload.get("due_date"))
    for row in models:
        title = str(row.get("title") or "").strip()
        code = str(row.get("code") or "").strip().upper()
        if not title or not code:
            raise DesignError("Cada modelo precisa de peça e referência.")
        if db.query(Development).filter_by(company_id=company_id, code=code).first():
            raise DesignError(f"Já existe um desenvolvimento com a referência {code}.")
        user_ids = [int(item) for item in (row.get("user_ids") or []) if item]
        users = [db.get(User, user_id) for user_id in user_ids]
        users = [user for user in users if user]
        quantity = row.get("quantity") if row.get("quantity") not in (None, "") else row.get("requested_quantity")
        development = Development(
            company_id=company_id,
            customer_id=customer_id,
            code=code,
            title=title,
            owner_name=owner_name_for(users),
            cover_url=row.get("cover_url") or None,
            images=[row["cover_url"]] if row.get("cover_url") else [],
            request_source=payload.get("request_source") or "outro",
            request_group=payload.get("request_group") or None,
            requested_quantity=int(quantity) if quantity else None,
            request_notes=payload.get("request_notes") or None,
            current_stage="novo",
            status=ACTIVE,
            due_date=due_date,
        )
        db.add(development)
        db.flush()
        _add_stage_event(db, development, "novo")
        for index, user in enumerate(users):
            db.add(DevelopmentAssignee(
                development_id=development.id,
                user_id=user.id,
                role="principal" if index == 0 else "parceria",
            ))
        created.append(development)
    db.commit()
    return [get_development(db, company_id, item.id) for item in created]


def move_development(db: Session, company_id: int, development_id: int, payload: dict) -> Development:
    development = get_development(db, company_id, development_id)
    to_stage = str(payload.get("to_stage") or "")
    if to_stage not in STAGE_IDS:
        raise DesignError("Fase inválida")
    if to_stage == "aprovado" and development.current_stage != "resposta_cliente":
        raise DesignError("A aprovação só pode ser registada depois do envio e da resposta do cliente.")
    if to_stage == "retificacoes" and development.current_stage != "resposta_cliente":
        raise DesignError("As retificações devem partir de uma resposta do cliente.")
    now = utcnow()
    closing_note = None
    if development.status in STATUS_HISTORY:
        closing_note = f"Ao sair, {STATUS_HISTORY[development.status]}" + (
            f": {development.waiting_reason}" if development.waiting_reason else "."
        )
    if not payload.get("keep_previous_active"):
        for event in development.stage_events:
            if event.status == "active" and event.ended_at is None:
                event.status = "completed"
                event.ended_at = now
                if closing_note:
                    event.note = f"{event.note} | {closing_note}" if event.note else closing_note
    planned = next((event for event in development.stage_events if event.stage == to_stage and event.status == "planned"), None)
    note = payload.get("note")
    responsible = payload.get("responsible_name") or development.owner_name
    if planned:
        planned.status = "active"
        planned.started_at = now
        planned.ended_at = None
        if note:
            planned.note = note
        if payload.get("supplier_id"):
            planned.supplier_id = payload["supplier_id"]
        planned.responsible_name = responsible
    else:
        db.add(DevelopmentStageEvent(
            development_id=development.id,
            stage=to_stage,
            status="active",
            started_at=now,
            note=note,
            supplier_id=payload.get("supplier_id"),
            responsible_name=responsible,
        ))
    development.current_stage = to_stage
    if to_stage == "aprovado":
        development.status = COMPLETED
    elif to_stage == "resposta_cliente":
        development.status = WAITING_CLIENT
    else:
        development.status = ACTIVE
    development.waiting_reason = None
    if to_stage in PHASE_TWO:
        ensure_style(db, development)
    elif development.style_id:
        ensure_style(db, development)
    db.commit()
    return get_development(db, company_id, development.id)


def patch_development(db: Session, company_id: int, development_id: int, payload: dict) -> Development:
    development = get_development(db, company_id, development_id)
    data = {key: value for key, value in payload.items() if key in PATCHABLE}
    if "due_date" in data:
        data["due_date"] = _parse_date(data["due_date"])
    if "images" in data and data["images"] is not None:
        data["images"] = list(dict.fromkeys(data["images"] or []))
    if "status" in data and data["status"]:
        allowed = {ACTIVE, WAITING_SUPPLIER, WAITING_CLIENT, BLOCKED, COMPLETED, "cancelled", REJECTED}
        if data["status"] not in allowed:
            raise DesignError("Estado inválido")
    for key, value in data.items():
        setattr(development, key, value)
    if development.style_id:
        ensure_style(db, development)
    db.commit()
    return get_development(db, company_id, development.id)


def add_assignee(db: Session, company_id: int, development_id: int, payload: dict) -> Development:
    development = get_development(db, company_id, development_id)
    role = payload.get("role") or "parceria"
    if role not in ASSIGNEE_ROLES:
        raise DesignError("Função inválida")
    user = db.get(User, int(payload.get("user_id") or 0))
    if not user:
        raise DesignError("Utilizador não encontrado", 404)
    exists = db.query(DevelopmentAssignee).filter_by(development_id=development.id, user_id=user.id, role=role).first()
    if exists:
        raise DesignError("Esta pessoa já tem essa função", 409)
    db.add(DevelopmentAssignee(development_id=development.id, user_id=user.id, role=role))
    if not development.owner_name or development.owner_name == "Por distribuir":
        development.owner_name = user.full_name
    elif user.full_name not in development.owner_name:
        development.owner_name = f"{development.owner_name} + {user.full_name}"
    db.commit()
    return get_development(db, company_id, development.id)


def remove_assignee(db: Session, company_id: int, development_id: int, assignee_id: int) -> None:
    development = get_development(db, company_id, development_id)
    item = db.get(DevelopmentAssignee, assignee_id)
    if not item or item.development_id != development.id:
        raise DesignError("Responsável não encontrado", 404)
    db.delete(item)
    db.commit()


def add_task(db: Session, company_id: int, development_id: int, payload: dict) -> Development:
    development = get_development(db, company_id, development_id)
    kind = payload.get("kind") or "ficha"
    status = payload.get("status") or "pending"
    if kind not in TASK_KINDS or status not in TASK_STATUSES:
        raise DesignError("Tipo ou estado de pendência inválido")
    user_id = payload.get("responsible_user_id")
    if user_id and not db.get(User, int(user_id)):
        raise DesignError("Utilizador não encontrado", 404)
    task = DevelopmentTask(
        development_id=development.id,
        kind=kind,
        status=status,
        note=payload.get("note"),
        due_date=_parse_date(payload.get("due_date")),
        responsible_user_id=int(user_id) if user_id else None,
        completed_at=utcnow() if status == "done" else None,
    )
    db.add(task)
    db.commit()
    return get_development(db, company_id, development.id)


def update_task(db: Session, company_id: int, development_id: int, task_id: int, payload: dict) -> Development:
    development = get_development(db, company_id, development_id)
    task = db.get(DevelopmentTask, task_id)
    if not task or task.development_id != development.id:
        raise DesignError("Pendência não encontrada", 404)
    if payload.get("status") and payload["status"] not in TASK_STATUSES:
        raise DesignError("Estado de pendência inválido")
    if payload.get("responsible_user_id") and not db.get(User, int(payload["responsible_user_id"])):
        raise DesignError("Utilizador não encontrado", 404)
    if "status" in payload:
        task.completed_at = utcnow() if payload["status"] == "done" else None
    for key in ("status", "note", "responsible_user_id"):
        if key in payload:
            setattr(task, key, payload[key] if key != "responsible_user_id" or not payload[key] else int(payload[key]))
    if "due_date" in payload:
        task.due_date = _parse_date(payload.get("due_date"))
    db.commit()
    return get_development(db, company_id, development.id)


def remove_task(db: Session, company_id: int, development_id: int, task_id: int) -> None:
    development = get_development(db, company_id, development_id)
    task = db.get(DevelopmentTask, task_id)
    if not task or task.development_id != development.id:
        raise DesignError("Pendência não encontrada", 404)
    db.delete(task)
    db.commit()


def add_comment(db: Session, company_id: int, development_id: int, payload: dict, author: str) -> Development:
    development = get_development(db, company_id, development_id)
    body = str(payload.get("body") or "").strip()
    if not body:
        raise DesignError("Escreva o comentário.")
    db.add(DevelopmentComment(
        development_id=development.id,
        author=payload.get("author") or author or "Utilizador",
        body=body,
        category=payload.get("category") or "nota_interna",
    ))
    db.commit()
    return get_development(db, company_id, development.id)


def upsert_stage_note(db: Session, company_id: int, development_id: int, payload: dict) -> Development:
    development = get_development(db, company_id, development_id)
    stage = payload.get("stage")
    if stage not in STAGE_IDS:
        raise DesignError("Fase inválida")
    events = [event for event in development.stage_events if event.stage == stage]
    if events:
        max(events, key=lambda event: event.started_at or utcnow()).note = payload.get("note")
    else:
        db.add(DevelopmentStageEvent(
            development_id=development.id, stage=stage, status="planned",
            note=payload.get("note"), responsible_name=development.owner_name,
        ))
    db.commit()
    return get_development(db, company_id, development.id)


def update_stage_note(db: Session, company_id: int, development_id: int, event_id: int, note: str | None) -> Development:
    development = get_development(db, company_id, development_id)
    event = db.get(DevelopmentStageEvent, event_id)
    if not event or event.development_id != development.id:
        raise DesignError("Fase não encontrada", 404)
    event.note = note
    db.commit()
    return get_development(db, company_id, development.id)


def delete_development(db: Session, company_id: int, development_id: int) -> None:
    development = get_development(db, company_id, development_id)
    if development.production_order_id:
        raise DesignError("Tem produção associada. Cancele o desenvolvimento em vez de o apagar.", 409)
    db.delete(development)
    db.commit()


def create_production(db: Session, company_id: int, development_id: int, payload: dict) -> dict:
    development = get_development(db, company_id, development_id)
    if development.current_stage != "aprovado":
        raise DesignError("A amostra tem de estar aprovada antes de seguir para produção.", 409)
    quantity = float(payload.get("quantity") or development.production_quantity or 0)
    if quantity <= 0:
        raise DesignError("Indique uma quantidade válida.")
    style = ensure_style(db, development)
    if development.production_order_id:
        existing = db.get(ProductionOrder, development.production_order_id)
        if existing and existing.company_id == company_id:
            return {"production_order_id": existing.id, "order_no": existing.order_no, "already_released": True}
    order_no = str(payload.get("order_no") or "").strip() or f"OF-{development.code}"
    if db.query(ProductionOrder).filter_by(company_id=company_id, order_no=order_no).first():
        raise DesignError("Já existe uma ordem com esse número.", 409)
    order = ProductionOrder(
        company_id=company_id,
        style_id=style.id,
        line_id=payload.get("line_id"),
        order_no=order_no,
        quantity=quantity,
        planned_end=_parse_date(payload.get("planned_end")) or development.due_date,
        priority=int(payload.get("priority") or 3),
        status="planned",
        current_stage="planning",
        custom_data={"source": "approved_development", "development_id": development.id},
    )
    db.add(order)
    db.flush()
    if not development.sample_id:
        sample = Sample(
            company_id=company_id,
            style_id=style.id,
            sample_type="pps",
            version="V1",
            status="approved",
            comments=f"Aprovado a partir de {development.code}",
            custom_data={"development_id": development.id, "production_order_id": order.id},
        )
        db.add(sample)
        db.flush()
        development.sample_id = sample.id
    development.production_order_id = order.id
    development.production_quantity = int(quantity)
    db.commit()
    return {"production_order_id": order.id, "order_no": order.order_no, "already_released": False, "style_id": style.id}


def today_dashboard(db: Session, company_id: int) -> dict:
    items = [serialize_development(row) for row in list_developments(db, company_id)]
    open_items = [item for item in items if not item["archived"] and item["current_stage"] != "aprovado" and item["status"] not in CLOSED_STATUSES]
    for item in open_items:
        item["priority"] = priority_score(item)
    priorities = sorted([item for item in open_items if item["priority"] > 0], key=lambda row: row["priority"], reverse=True)[:8]
    overdue = [item for item in open_items if item["due_date"] and item["due_date"] < date.today().isoformat()]
    return {
        "overdue_count": len(overdue),
        "blocked_count": sum(1 for item in open_items if item["status"] == BLOCKED),
        "waiting_supplier_count": sum(1 for item in open_items if item["status"] == WAITING_SUPPLIER),
        "waiting_client_count": sum(1 for item in open_items if item["status"] == WAITING_CLIENT),
        "active_count": len(open_items),
        "approved_count": sum(1 for item in items if item["current_stage"] == "aprovado"),
        "unassigned_count": sum(1 for item in open_items if not item["owner_name"] or item["owner_name"] == "Por distribuir"),
        "priorities": priorities,
        "overdue": overdue[:8],
    }


def organization_board(db: Session, company_id: int) -> dict:
    items = [serialize_development(row) for row in list_developments(db, company_id)]
    active = [item for item in items if not item["archived"]]
    by_owner: dict[str, list] = defaultdict(list)
    by_client: dict[str, list] = defaultdict(list)
    unassigned = []
    for item in active:
        owner = item["owner_name"] or "Por distribuir"
        if owner == "Por distribuir" and not item["assignees"]:
            unassigned.append(item)
        by_owner[owner].append(item)
        by_client[item["customer_name"] or "Sem cliente"].append(item)

    def pack(name, rows):
        open_rows = [row for row in rows if row["current_stage"] != "aprovado" and row["status"] not in CLOSED_STATUSES]
        return {
            "name": name,
            "total": len(rows),
            "open": len(open_rows),
            "overdue": sum(1 for row in open_rows if row["due_date"] and row["due_date"] < date.today().isoformat()),
            "waiting": sum(1 for row in open_rows if row["status"] in WAITING_STATUSES),
            "high_risk": sum(1 for row in open_rows if row["risk"] == "high"),
            "items": rows,
        }

    designers = [pack(name, rows) for name, rows in sorted(by_owner.items(), key=lambda pair: (-len(pair[1]), pair[0]))]
    clients = [pack(name, rows) for name, rows in sorted(by_client.items(), key=lambda pair: (-len(pair[1]), pair[0]))]
    return {"designers": designers, "clients": clients, "unassigned": unassigned, "total_open": sum(item["open"] for item in designers)}


def period_report(db: Session, company_id: int, start: date | None, end: date | None) -> dict:
    today = date.today()
    start = start or today.replace(day=1)
    end = end or today
    if end < start:
        start, end = end, start
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time())
    rows = list_developments(db, company_id)

    def in_period(item: Development) -> bool:
        created = item.created_at
        if not created:
            return False
        if getattr(created, "tzinfo", None):
            created = created.replace(tzinfo=None)
        return start_dt <= created < end_dt

    period = [item for item in rows if in_period(item)]
    by_client: dict[str, int] = defaultdict(int)
    by_stage: dict[str, int] = defaultdict(int)
    by_owner: dict[str, int] = defaultdict(int)
    for item in period:
        by_client[item.customer.name if item.customer else "—"] += 1
        by_stage[item.current_stage] += 1
        by_owner[item.owner_name or "Por distribuir"] += 1
    approved = [item for item in period if item.current_stage == "aprovado"]
    productions = [item for item in period if item.production_order_id]
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "developments": {
            "total": len(period),
            "approved": len(approved),
            "by_client": [{"name": name, "count": count} for name, count in sorted(by_client.items(), key=lambda pair: -pair[1])],
            "by_stage": [{"id": stage, "count": by_stage.get(stage, 0)} for stage in STAGE_IDS],
            "by_designer": [{"name": name, "count": count} for name, count in sorted(by_owner.items(), key=lambda pair: -pair[1])],
        },
        "productions": {"total": len(productions), "quantity": sum(item.production_quantity or 0 for item in productions)},
    }


def company_team(db: Session, company_id: int) -> list[dict]:
    rows = (
        db.query(User, UserCompany)
        .join(UserCompany, UserCompany.user_id == User.id)
        .filter(UserCompany.company_id == company_id, User.active.is_(True))
        .order_by(User.full_name)
        .all()
    )
    team = []
    for user, membership in rows:
        team.append({
            "id": user.id,
            "name": user.full_name,
            "role": membership.role,
            "initials": initials_for([user]),
        })
    return team
