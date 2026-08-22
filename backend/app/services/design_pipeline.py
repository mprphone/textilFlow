from datetime import date, datetime, timedelta, timezone

PIPELINE = [
    ("novo", "Pedido recebido"),
    ("proposta_cliente", "Referências e distribuição"),
    ("ficha_tecnica", "Ficha técnica"),
    ("desenvolvimento_malha", "Preparação materiais"),
    ("modelagem", "Modelagem"),
    ("corte", "Corte"),
    ("confecao", "Confeção"),
    ("finalizacao", "Finalização da amostra"),
    ("envio_cliente", "Envio cliente"),
    ("resposta_cliente", "Resposta cliente"),
    ("retificacoes", "Retificações"),
    ("aprovado", "Aprovado"),
]

STAGE_IDS = [item[0] for item in PIPELINE]
STAGE_LABELS = dict(PIPELINE)
PHASE_ONE = ["novo", "proposta_cliente"]
PHASE_TWO = [stage for stage in STAGE_IDS if stage not in PHASE_ONE]

ACTIVE = "active"
WAITING_SUPPLIER = "waiting_supplier"
WAITING_CLIENT = "waiting_client"
BLOCKED = "blocked"
COMPLETED = "completed"
CANCELLED = "cancelled"
REJECTED = "rejected"

CLOSED_STATUSES = {CANCELLED, REJECTED, COMPLETED}
WAITING_STATUSES = {WAITING_SUPPLIER, WAITING_CLIENT, BLOCKED}

TASK_KINDS = {
    "ficha": "Ficha técnica",
    "malha": "Malha",
    "tingimento": "Tingimento",
    "grafico_bordado": "Gráfico/bordado",
    "bordado": "Bordado",
    "aplicacao": "Aplicações",
    "acessorios": "Acessórios",
    "shopping_modelagem": "Shopping para modelagem",
    "envio_cliente": "Envio ao cliente",
    "resposta_cliente": "Resposta do cliente",
}
TASK_STATUSES = {"pending", "in_progress", "waiting", "done", "cancelled"}
ASSIGNEE_ROLES = {
    "principal": "Principal",
    "parceria": "Parceria",
    "fitting": "Fitting",
    "qualidade": "Qualidade",
    "grafico": "Gráfico",
}
REQUEST_SOURCES = {
    "whatsapp": "WhatsApp",
    "email": "Email",
    "reuniao": "Reunião",
    "telefone": "Telefone",
    "outro": "Outro",
}
STATUS_LABELS = {
    ACTIVE: "Em curso",
    WAITING_SUPPLIER: "Aguarda fornecedor",
    WAITING_CLIENT: "Aguarda cliente",
    BLOCKED: "Bloqueado",
    COMPLETED: "Aprovado",
    REJECTED: "Reprovado",
    CANCELLED: "Cancelado",
}

NEXT_ACTIONS = {
    "novo": "Registar pedido, fotografias e referências",
    "proposta_cliente": "Distribuir referências pelas designers",
    "ficha_tecnica": "Concluir a ficha técnica",
    "desenvolvimento_malha": "Tratar materiais e serviços em paralelo",
    "modelagem": "Validar moldes",
    "corte": "Concluir corte piloto",
    "confecao": "Terminar a confeção da amostra",
    "finalizacao": "Rever e finalizar a amostra",
    "envio_cliente": "Enviar a amostra ao cliente",
    "resposta_cliente": "Registar aprovação, retificação ou reprovação",
    "retificacoes": "Executar alterações pedidas pelo cliente",
    "aprovado": "Criar produção industrial",
}

DEFAULT_STAGE_DAYS = 3.0


class DesignError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.message = message
        self.status = status


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def active_stage_event(development):
    active = [
        event for event in development.stage_events
        if event.status == "active" and event.ended_at is None
    ]
    return max(active, key=lambda item: as_aware(item.started_at) or utcnow(), default=None)


def days_in_current_stage(development) -> float:
    event = active_stage_event(development)
    if not event:
        return 0
    started = as_aware(event.started_at) or utcnow()
    return round((utcnow() - started).total_seconds() / 86400, 1)


def get_next_action(development) -> str:
    if development.status == WAITING_SUPPLIER:
        return "Confirmar prazo com o fornecedor"
    if development.status == WAITING_CLIENT:
        return "Pedir resposta ao cliente"
    if development.status == BLOCKED:
        return "Resolver bloqueio"
    tasks = getattr(development, "tasks", []) or []
    waiting_task = next((task for task in tasks if task.status == "waiting"), None)
    if waiting_task:
        return f"Resolver pendência: {TASK_KINDS.get(waiting_task.kind, waiting_task.kind.replace('_', ' '))}"
    active_task = next((task for task in tasks if task.status in {"pending", "in_progress"}), None)
    if active_task:
        return f"Tratar pendência: {TASK_KINDS.get(active_task.kind, active_task.kind.replace('_', ' '))}"
    return NEXT_ACTIONS.get(development.current_stage, "Rever desenvolvimento")


def build_suggestions(development) -> list[str]:
    suggestions: list[str] = []
    days = days_in_current_stage(development)
    waiting_tasks = [task for task in getattr(development, "tasks", []) or [] if task.status == "waiting"]
    if waiting_tasks:
        names = ", ".join(TASK_KINDS.get(task.kind, task.kind.replace("_", " ")) for task in waiting_tasks[:2])
        suggestions.append(f"Pendências a aguardar: {names}.")
    if days >= 7 and development.status == ACTIVE:
        suggestions.append(f"Está há {days:.0f} dias nesta fase. Confirmar se existe bloqueio.")
    if development.status == WAITING_SUPPLIER and days >= 3:
        suggestions.append("Enviar lembrete ao fornecedor.")
    if development.status == WAITING_CLIENT and days >= 4:
        suggestions.append("Pedir decisão ao cliente e definir nova data de resposta.")
    if development.due_date:
        remaining = (development.due_date - date.today()).days
        if remaining < 0:
            suggestions.append(f"Prazo ultrapassado há {abs(remaining)} dias.")
        elif remaining <= 3 and development.current_stage not in {"envio_cliente", "aprovado"}:
            suggestions.append("Prazo em risco. Reorganizar prioridades hoje.")
    if development.current_stage == "aprovado" and not development.production_order_id:
        suggestions.append("Amostra aprovada. Criar produção com os dados já existentes.")
    return suggestions[:3]


def risk_from_suggestions(suggestions: list[str]) -> str:
    text = " ".join(suggestions).lower()
    if "ultrapassado" in text or "risco" in text:
        return "high"
    if suggestions:
        return "medium"
    return "low"


def is_archived(development) -> bool:
    if development.status in {REJECTED, CANCELLED}:
        return True
    return development.status == COMPLETED and development.current_stage != "aprovado"


def is_open(development) -> bool:
    return development.current_stage != "aprovado" and development.status not in CLOSED_STATUSES and not is_archived(development)


def priority_score(data: dict) -> int:
    score = {"high": 40, "medium": 20}.get(data.get("risk"), 0)
    due = data.get("due_date")
    if due:
        if isinstance(due, str):
            due = date.fromisoformat(due[:10])
        remaining = (due - date.today()).days
        if remaining < 0:
            score += 50 + min(20, -remaining * 2)
        elif remaining <= 3:
            score += 30
        elif remaining <= 7:
            score += 15
    status = data.get("status") or ""
    if status == BLOCKED:
        score += 25
    elif status.startswith("waiting"):
        score += 10
    score += min(15, int(data.get("days_in_stage") or 0))
    if data.get("estimated_value"):
        score += min(10, int(float(data["estimated_value"]) / 1000))
    return score


def average_stage_durations(events) -> dict[str, dict]:
    samples: dict[str, list[float]] = {}
    for event in events:
        if not event.ended_at or not event.started_at:
            continue
        started = as_aware(event.started_at)
        ended = as_aware(event.ended_at)
        samples.setdefault(event.stage, []).append((ended - started).total_seconds() / 86400)
    return {
        stage: {"average_days": round(sum(values) / len(values), 1), "completed_events": len(values)}
        for stage, values in samples.items()
    }


def estimate_completion(development, averages: dict[str, dict]) -> date | None:
    if development.current_stage == "aprovado":
        return None
    try:
        index = STAGE_IDS.index(development.current_stage)
    except ValueError:
        return None
    current_average = averages.get(development.current_stage, {}).get("average_days", DEFAULT_STAGE_DAYS)
    days = max(0.5, current_average - days_in_current_stage(development))
    for stage in STAGE_IDS[index + 1:]:
        if stage == "aprovado":
            continue
        days += averages.get(stage, {}).get("average_days", DEFAULT_STAGE_DAYS)
    return date.today() + timedelta(days=round(days))


def pipeline_catalog() -> dict:
    return {
        "pipeline": [{"id": stage, "label": label} for stage, label in PIPELINE],
        "phase_one": PHASE_ONE,
        "phase_two": PHASE_TWO,
        "status_labels": STATUS_LABELS,
        "task_kinds": TASK_KINDS,
        "task_statuses": {key: {"pending": "Pendente", "in_progress": "Em curso", "waiting": "A aguardar", "done": "Concluída", "cancelled": "Cancelada"}[key] for key in TASK_STATUSES},
        "assignee_roles": ASSIGNEE_ROLES,
        "request_sources": REQUEST_SOURCES,
        "next_actions": NEXT_ACTIONS,
    }
