from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import String, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import BOMItem, CapacityDay, CapacityEvent, Company, CostLine, CostSheet, Customer, CuttingJob, Employee, EmployeeSkill, ExternalCapacity, Machine, Material, ProductOperation, ProductionMaterialRequirement, ProductionOrder, ProductionRouteStep, PurchaseOrder, PurchaseOrderLine, Sample, SewingPlan, Style, StyleRevision, SubcontractJob, SubcontractService, User
from ...schemas import ProductionRouteStepIn
from ...services.primavera_sync import queue_master_record
from ...services.audit import record_audit
from ...services.costing import rebuild_product_cost, recalculate_sheet, refresh_style_costs
from ...services.production import employee_hourly_rate, refresh_employee_rate
from ...services.crud import apply_payload, coerce_value, resource_model
from ...services.proposal_release import ReleaseConflictError, release_order_reservations
from ...services.production_stage import create_batches_from_cutting, update_order_stage
from ...services.production_route import assert_route_ready, assign_route_step, build_route_status
from ...services.registry import RESOURCE_MODELS
from ...services.serialization import model_to_dict
from ..deps import current_user, require_company, require_resource_read, require_resource_write, require_role


router = APIRouter(prefix="/crud", tags=["Registos"])
IMMUTABLE_RESOURCES = {"audit", "inventory-movements", "production-events", "style-revisions"}


def _queue_primavera(db, company_id, resource, row):
    if resource not in {"customers", "suppliers", "materials", "banks"}:
        return
    try:
        company = db.get(Company, company_id)
        if not company:
            return
        result = queue_master_record(company, resource, row)
        if hasattr(row, "sync_status"):
            if result and result.get("status") == "sent":
                row.sync_status = "synced"
                if hasattr(row, "primavera_id"):
                    row.primavera_id = row.primavera_id or getattr(row, "code", None)
            elif result:
                row.sync_status = result.get("status") or "queued"
            else:
                row.sync_status = "local"
    except Exception:
        if hasattr(row, "sync_status"):
            row.sync_status = "failed"


def calculated_fields(db, instance):
    if isinstance(instance, CostLine):
        instance.amount = round((instance.quantity or 0) * (instance.unit_cost or 0), 4)
    elif isinstance(instance, Sample):
        if instance.responsible_employee_id and instance.labor_minutes and not instance.labor_cost:
            employee = db.get(Employee, instance.responsible_employee_id)
            instance.labor_cost = round((employee_hourly_rate(employee) / 60) * instance.labor_minutes, 4) if employee else 0
        instance.total_cost = round((instance.labor_cost or 0) + (instance.material_cost or 0) + (instance.external_cost or 0), 4)
    elif isinstance(instance, CuttingJob):
        if instance.duration_minutes:
            employee = db.get(Employee, instance.cutter_employee_id) if instance.cutter_employee_id else None
            machine = db.get(Machine, instance.machine_id) if instance.machine_id else None
            instance.labor_cost = round((employee_hourly_rate(employee) / 60) * instance.duration_minutes, 4)
            instance.machine_cost = round(((machine.hourly_cost if machine else 0) / 60) * instance.duration_minutes, 4)
        if instance.actual_fabric:
            instance.waste_pct = round(max(0, (instance.actual_fabric - (instance.planned_fabric or 0)) / instance.actual_fabric * 100), 2)
        if instance.status in {"completed", "done"} or float(instance.good_pieces or 0) >= float(instance.planned_pieces or 0) * 0.99:
            create_batches_from_cutting(db, instance)
            order = db.get(ProductionOrder, instance.production_order_id) if instance.production_order_id else None
            update_order_stage(db, order)
    elif isinstance(instance, SubcontractJob):
        _prepare_subcontract_job(db, instance)
    elif isinstance(instance, CapacityDay):
        if not instance.shift_id:
            raise HTTPException(422, "Escolha o turno do dia de capacidade")
        if any((value or 0) < 0 for value in [instance.scheduled_employees, instance.absent_employees, instance.minutes_per_employee, instance.break_minutes, instance.setup_minutes, instance.maintenance_minutes]):
            raise HTTPException(422, "Os valores de capacidade não podem ser negativos")
        if (instance.absent_employees or 0) > (instance.scheduled_employees or 0):
            raise HTTPException(422, "As ausências não podem exceder as pessoas previstas")
        if not 0 <= (instance.efficiency_pct or 0) <= 150:
            raise HTTPException(422, "A eficiência deve estar entre 0% e 150%")
    elif isinstance(instance, CapacityEvent):
        employee = db.get(Employee, instance.employee_id) if instance.employee_id else None
        machine = db.get(Machine, instance.machine_id) if instance.machine_id else None
        if not instance.line_id:
            instance.line_id = employee.line_id if employee else machine.line_id if machine else None
        reducing = {"absence", "holiday", "vacation", "training", "meeting", "maintenance"}
        if instance.event_type in reducing:
            instance.minutes_delta = -abs(instance.minutes_delta or 480)
        elif instance.event_type == "overtime":
            instance.minutes_delta = abs(instance.minutes_delta or 0)
    elif isinstance(instance, EmployeeSkill):
        if not 1 <= (instance.proficiency_level or 0) <= 5:
            raise HTTPException(422, "O nível de competência deve estar entre 1 e 5")
        if not 0 <= (instance.efficiency_pct or 0) <= 150:
            raise HTTPException(422, "A eficiência deve estar entre 0% e 150%")
    elif isinstance(instance, ExternalCapacity):
        if (instance.capacity_units or 0) < 0 or (instance.reserved_units or 0) < 0 or (instance.unit_cost or 0) < 0:
            raise HTTPException(422, "Capacidade, reserva e custo não podem ser negativos")
        if not 0 <= (instance.reliability_pct or 0) <= 100:
            raise HTTPException(422, "A fiabilidade deve estar entre 0% e 100%")
    elif isinstance(instance, Employee):
        refresh_employee_rate(instance)
    elif isinstance(instance, SewingPlan):
        order = db.get(ProductionOrder, instance.production_order_id) if instance.production_order_id else None
        if order:
            instance.style_id = instance.style_id or order.style_id
            instance.line_id = instance.line_id or order.line_id
            instance.quantity = instance.quantity or max(0, (order.quantity or 0) - (order.completed_quantity or 0))
        if not instance.sam_minutes and instance.style_id:
            instance.sam_minutes = round(sum(
                row.smv or 0 for row in db.query(ProductOperation).filter_by(style_id=instance.style_id).all()
            ), 4)
        if instance.status == "backlog":
            instance.start_date = instance.start_date or date.today()
            instance.end_date = instance.end_date or instance.start_date
            instance.allocation_type = instance.allocation_type or "internal"
        if not instance.start_date or not instance.end_date:
            raise HTTPException(422, "Indique as datas inicial e final")
        if instance.end_date < instance.start_date:
            raise HTTPException(422, "A data final não pode ser anterior à data inicial")
        if not 0 < (instance.efficiency_pct or 0) <= 150:
            raise HTTPException(422, "A eficiência deve estar entre 0% e 150%")
        if not 0 <= (instance.probability_pct or 0) <= 100:
            raise HTTPException(422, "A probabilidade deve estar entre 0% e 100%")
        if instance.allocation_type == "internal" and not instance.line_id and instance.status != "backlog":
            raise HTTPException(422, "Escolha a linha para uma produção interna")
        if instance.allocation_type == "external" and not instance.supplier_id:
            raise HTTPException(422, "Escolha a confeção externa")
        if (instance.quantity or 0) <= 0 or (instance.sam_minutes or 0) <= 0:
            raise HTTPException(422, "Indique uma quantidade e um SAM válidos")
        instance.required_minutes = round(
            (instance.quantity or 0) * (instance.sam_minutes or 0) / (instance.efficiency_pct / 100), 2
        )


def _prepare_subcontract_job(db, instance):
    service = db.get(SubcontractService, instance.subcontract_service_id)
    if not service or service.company_id != instance.company_id:
        raise HTTPException(422, "Serviço subcontratado inválido")
    instance.supplier_id = service.supplier_id
    if not (instance.unit or "").strip():
        instance.unit = service.unit or "un"
    if not instance.unit_cost:
        instance.unit_cost = service.unit_cost or 0
    if instance.production_order_id and not instance.quantity:
        order = db.get(ProductionOrder, instance.production_order_id)
        if order and order.company_id == instance.company_id:
            instance.quantity = max(0, (order.quantity or 0) - (order.completed_quantity or 0))
    if (instance.quantity or 0) < 0:
        raise HTTPException(422, "A quantidade enviada não pode ser negativa")
    if instance.status not in {"planned", "sent", "partial", "received", "problem", "cancelled"}:
        raise HTTPException(422, "Estado de subcontrato inválido")
    if instance.status == "sent" and not instance.sent_date:
        instance.sent_date = date.today()
    if instance.status in {"received", "partial"} and not instance.received_date:
        instance.received_date = date.today()
    if instance.sent_date and not instance.expected_date and (service.lead_time_days or 0) > 0:
        instance.expected_date = instance.sent_date + timedelta(days=int(service.lead_time_days))
    if instance.status == "received" and not instance.accepted_quantity and not instance.rejected_quantity:
        instance.accepted_quantity = instance.quantity or 0
    if instance.status == "partial":
        handled = (instance.accepted_quantity or 0) + (instance.rejected_quantity or 0)
        if handled <= 0:
            raise HTTPException(422, "Na receção parcial indique as quantidades aceites ou rejeitadas")
        if handled >= (instance.quantity or 0) > 0:
            instance.status = "received"
    if not (instance.reference or "").strip():
        prefix = date.today().strftime("EXT-%Y%m%d-")
        existing = db.query(SubcontractJob).filter(
            SubcontractJob.company_id == instance.company_id,
            SubcontractJob.reference.like(f"{prefix}%"),
        ).count()
        instance.reference = f"{prefix}{existing + 1:03d}"
    instance.planned_cost = round((instance.quantity or 0) * (instance.unit_cost or 0), 4)

    order = db.get(ProductionOrder, instance.production_order_id) if instance.production_order_id else None
    if order and order.style_id:
        assign_route_step(db, instance, order)
        if instance.chain_step_sequence and instance.status in {"planned", "sent"}:
            check = assert_route_ready(db, order, step_type="subcontract", subcontract_service_id=instance.subcontract_service_id, override=True)
            if not check["ready"] and instance.status == "sent":
                # Guardar aviso sem bloquear a criação via API genérica; o distribute já bloqueia.
                instance.notes = (instance.notes or "") + " [AVISO: passo anterior não concluído]"
    if instance.status == "sent" and instance.production_order_id:
        stage = {"dyeing": "dyeing", "printing": "printing", "cutting": "cutting", "sewing": "confeção"}.get(service.category)
        if order and order.company_id == instance.company_id and stage:
            if (order.current_stage or "planning").lower() in {"planning", "backlog", "planned"}:
                order.current_stage = stage


def protect_approved_cost(db, instance):
    sheet = instance if isinstance(instance, CostSheet) else db.get(CostSheet, instance.cost_sheet_id) if isinstance(instance, CostLine) else None
    if sheet and sheet.status in {"approved", "production"}:
        raise HTTPException(409, "A proposta aprovada está congelada. Duplique-a para criar uma revisão.")


def validate_cost_tenant_links(db, instance, company_id: int):
    if isinstance(instance, CostSheet):
        style = db.get(Style, instance.style_id) if instance.style_id else None
        if not style or style.company_id != company_id:
            raise HTTPException(422, "O artigo da ficha de custo nao pertence a esta empresa")
        customer_id = (instance.custom_data or {}).get("customer_id")
        if customer_id:
            customer = db.get(Customer, customer_id)
            if not customer or customer.company_id != company_id:
                raise HTTPException(422, "O cliente da ficha de custo nao pertence a esta empresa")
    elif isinstance(instance, CostLine):
        sheet = db.get(CostSheet, instance.cost_sheet_id) if instance.cost_sheet_id else None
        if not sheet or sheet.company_id != company_id:
            raise HTTPException(422, "A ficha de custo nao pertence a esta empresa")
        source_type = (instance.source_type or "").lower()
        if source_type == "bom" and instance.source_id:
            source = db.get(BOMItem, instance.source_id)
            if not source or source.company_id != company_id or source.style_id != sheet.style_id:
                raise HTTPException(422, "A origem BOM nao pertence a esta ficha de custo")
        elif source_type == "revision" and instance.source_id:
            source = db.get(CostLine, instance.source_id)
            source_sheet = db.get(CostSheet, source.cost_sheet_id) if source else None
            if not source or not source_sheet or source.company_id != company_id or source_sheet.style_id != sheet.style_id:
                raise HTTPException(422, "A revisao de custo nao pertence a este artigo")
        elif "operation" in source_type and instance.source_id:
            source = db.get(ProductOperation, instance.source_id)
            if not source or source.company_id != company_id or source.style_id != sheet.style_id:
                raise HTTPException(422, "A operacao da linha de custo nao pertence a este artigo")
        elif source_type == "subcontract_service" and instance.source_id:
            source = db.get(SubcontractService, instance.source_id)
            if not source or source.company_id != company_id:
                raise HTTPException(422, "O servico externo nao pertence a esta empresa")
        elif instance.category == "material" and instance.source_id:
            source = db.get(Material, instance.source_id)
            if not source or source.company_id != company_id:
                raise HTTPException(422, "O material da linha de custo nao pertence a esta empresa")


def protect_released_order(db, instance, payload: dict | None = None, *, deleting: bool = False):
    if not isinstance(instance, ProductionOrder):
        return
    has_requirements = db.query(ProductionMaterialRequirement.id).filter_by(
        production_order_id=instance.id
    ).first()
    if not has_requirements:
        return
    if deleting:
        raise HTTPException(409, "Uma OF criada por proposta nao pode ser eliminada; cancele-a para libertar as reservas")
    payload = payload or {}
    structural = {"sales_order_line_id", "style_id", "order_no", "quantity"}
    def changed(key):
        if key not in payload:
            return False
        incoming, current = payload[key], getattr(instance, key)
        if key in {"sales_order_line_id", "style_id"}:
            return (int(incoming) if incoming not in {None, ""} else None) != current
        if key == "quantity":
            return abs(float(incoming or 0) - float(current or 0)) > 1e-9
        return str(incoming or "") != str(current or "")
    if any(changed(key) for key in structural):
        raise HTTPException(409, "Quantidade, artigo e documentos de uma OF com consumos gerados ficam congelados")
    new_status = payload.get("status", instance.status)
    if instance.status == "cancelled" and new_status != "cancelled":
        raise HTTPException(409, "Uma OF cancelada com reservas libertadas nao pode ser reaberta diretamente")
    if new_status == "cancelled" and instance.status != "cancelled":
        try:
            release_order_reservations(db, instance)
        except ReleaseConflictError as exc:
            raise HTTPException(409, str(exc)) from exc


def update_related_costs(db, instance, *, created: bool = False):
    if isinstance(instance, CostLine):
        sheet = db.get(CostSheet, instance.cost_sheet_id)
        if sheet:
            recalculate_sheet(db, sheet)
    elif isinstance(instance, CostSheet):
        rebuild_product_cost(db, instance) if created else recalculate_sheet(db, instance)
    elif isinstance(instance, (BOMItem, ProductOperation)):
        refresh_style_costs(db, instance.style_id)
    elif isinstance(instance, PurchaseOrderLine):
        order = db.get(PurchaseOrder, instance.purchase_order_id)
        if order:
            lines = db.query(PurchaseOrderLine).filter_by(purchase_order_id=order.id).all()
            order.total = round(sum((line.quantity or 0) * (line.unit_cost or 0) for line in lines), 2)


@router.get("/meta/resources")
def resource_metadata(user: User = Depends(current_user)):
    result = {}
    for name, model in RESOURCE_MODELS.items():
        result[name] = [{
            "name": column.key,
            "type": type(column.type).__name__.lower(),
            "required": not column.nullable and column.default is None and column.server_default is None and not column.primary_key,
            "primary_key": column.primary_key,
            "foreign_key": next(iter(column.foreign_keys)).target_fullname if column.foreign_keys else None,
        } for column in inspect(model).columns]
    return result


@router.get("/{resource}")
def list_records(
    resource: str, request: Request, company_id: int, search: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000), offset: int = Query(default=0, ge=0),
    sort: str | None = None, direction: str = "desc",
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    require_resource_read(db, user, company_id, resource)
    model = resource_model(resource)
    columns = {column.key: column for column in inspect(model).columns}
    query = db.query(model)
    if "company_id" in columns:
        query = query.filter(model.company_id == company_id)
    for key, value in request.query_params.items():
        if key in {"company_id", "search", "limit", "offset", "sort", "direction"} or key not in columns or value == "":
            continue
        try:
            parsed = coerce_value(columns[key], value)
        except (TypeError, ValueError):
            continue
        query = query.filter(getattr(model, key) == parsed)
    if search:
        string_columns = [getattr(model, column.key) for column in columns.values() if isinstance(column.type, String)]
        if string_columns:
            query = query.filter(or_(*[column.ilike(f"%{search}%") for column in string_columns]))
    order_column = getattr(model, sort, None) if sort in columns else getattr(model, "created_at", None)
    if order_column is None:
        order_column = getattr(model, "id")
    ordering = order_column.asc() if direction.lower() == "asc" else order_column.desc()
    rows = query.order_by(ordering).offset(offset).limit(limit).all()
    return [model_to_dict(row) for row in rows]


@router.get("/{resource}/{item_id}")
def get_record(resource: str, item_id: int, company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_resource_read(db, user, company_id, resource)
    model = resource_model(resource)
    row = db.get(model, item_id)
    if not row or (hasattr(row, "company_id") and row.company_id != company_id):
        raise HTTPException(404, "Registo não encontrado")
    return model_to_dict(row)


@router.post("/{resource}", status_code=201)
def create_record(resource: str, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    company_id = int(payload.get("company_id") or 0)
    if resource in IMMUTABLE_RESOURCES:
        raise HTTPException(405, "Este recurso só pode ser criado pelo respetivo fluxo operacional")
    require_resource_write(db, user, company_id, resource)
    model = resource_model(resource)
    row = apply_payload(model(), payload, company_id=company_id)
    validate_cost_tenant_links(db, row, company_id)
    if isinstance(row, CostSheet) and row.status != "draft":
        raise HTTPException(405, "A aprovação de propostas só pode ser feita no fluxo de Costing")
    protect_approved_cost(db, row)
    calculated_fields(db, row)
    try:
        db.add(row)
        db.flush()
        update_related_costs(db, row, created=True)
        record_audit(db, company_id=company_id, user_id=user.id, entity=resource, entity_id=row.id, action="create", payload=payload)
        db.commit()
        db.refresh(row)
        _queue_primavera(db, company_id, resource, row)
        db.commit()
        return model_to_dict(row)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Registo duplicado ou relacionado com dados inválidos") from exc


@router.put("/{resource}/{item_id}")
def update_record(resource: str, item_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if resource in IMMUTABLE_RESOURCES:
        raise HTTPException(405, "O histórico operacional é imutável")
    model = resource_model(resource)
    row = db.get(model, item_id)
    if not row:
        raise HTTPException(404, "Registo não encontrado")
    company_id = getattr(row, "company_id", int(payload.get("company_id") or 0))
    require_resource_write(db, user, company_id, resource)
    protect_approved_cost(db, row)
    protect_released_order(db, row, payload)
    if isinstance(row, CostLine) and "cost_sheet_id" in payload and int(payload.get("cost_sheet_id") or 0) != row.cost_sheet_id:
        raise HTTPException(409, "Uma linha de custo nao pode ser movida para outra ficha")
    if isinstance(row, CostSheet) and "style_id" in payload and int(payload.get("style_id") or 0) != row.style_id:
        raise HTTPException(409, "Uma ficha de custo nao pode ser movida para outro artigo")
    if isinstance(row, CostSheet) and payload.get("status", row.status) != "draft":
        raise HTTPException(405, "A aprovação de propostas só pode ser feita no fluxo de Costing")
    if isinstance(row, Style):
        db.add(StyleRevision(
            company_id=company_id, style_id=row.id, version=row.technical_version,
            snapshot=model_to_dict(row), reason=payload.pop("revision_reason", "Alteração da ficha"), user_id=user.id,
        ))
        row.technical_version += 1
    apply_payload(row, payload, company_id=company_id)
    validate_cost_tenant_links(db, row, company_id)
    protect_approved_cost(db, row)
    calculated_fields(db, row)
    try:
        db.flush()
        update_related_costs(db, row)
        record_audit(db, company_id=company_id, user_id=user.id, entity=resource, entity_id=item_id, action="update", payload=payload)
        db.commit()
        db.refresh(row)
        _queue_primavera(db, company_id, resource, row)
        db.commit()
        return model_to_dict(row)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Alteração incompatível com outros registos") from exc


@router.delete("/{resource}/{item_id}", status_code=204)
def delete_record(resource: str, item_id: int, company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if resource in IMMUTABLE_RESOURCES:
        raise HTTPException(405, "O histórico operacional é imutável")
    require_role(db, user, company_id, {"admin", "manager"})
    model = resource_model(resource)
    row = db.get(model, item_id)
    if not row or (hasattr(row, "company_id") and row.company_id != company_id):
        raise HTTPException(404, "Registo não encontrado")
    protect_approved_cost(db, row)
    protect_released_order(db, row, deleting=True)
    try:
        cost_sheet_id = row.cost_sheet_id if isinstance(row, CostLine) else None
        style_id = row.style_id if isinstance(row, (BOMItem, ProductOperation)) else None
        purchase_order_id = row.purchase_order_id if isinstance(row, PurchaseOrderLine) else None
        db.delete(row)
        db.flush()
        if cost_sheet_id:
            sheet = db.get(CostSheet, cost_sheet_id)
            if sheet:
                recalculate_sheet(db, sheet)
        if style_id:
            refresh_style_costs(db, style_id)
        if purchase_order_id:
            order = db.get(PurchaseOrder, purchase_order_id)
            if order:
                lines = db.query(PurchaseOrderLine).filter_by(purchase_order_id=order.id).all()
                order.total = round(sum((line.quantity or 0) * (line.unit_cost or 0) for line in lines), 2)
        record_audit(db, company_id=company_id, user_id=user.id, entity=resource, entity_id=item_id, action="delete")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "O registo está em utilização e não pode ser eliminado") from exc


@router.get("/styles/{style_id}/production-route")
def list_production_route(style_id: int, company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    style = db.get(Style, style_id)
    if not style or style.company_id != company_id:
        raise HTTPException(404, "Modelo não encontrado")
    require_resource_read(db, user, company_id, "subcontract_services")
    steps = (
        db.query(ProductionRouteStep)
        .filter_by(style_id=style_id)
        .order_by(ProductionRouteStep.sequence)
        .all()
    )
    services = {row.id: row for row in db.query(SubcontractService).filter_by(company_id=company_id).all()}
    return [
        {
            "id": step.id,
            "sequence": step.sequence,
            "step_type": step.step_type,
            "subcontract_service_id": step.subcontract_service_id,
            "service": {"id": s.id, "code": s.code, "name": s.name, "category": s.category, "supplier_id": s.supplier_id}
            if (s := services.get(step.subcontract_service_id)) else None,
            "is_required": step.is_required,
            "notes": step.notes,
        }
        for step in steps
    ]


@router.post("/styles/{style_id}/production-route", status_code=201)
def save_production_route(style_id: int, company_id: int, payload: list[ProductionRouteStepIn], db: Session = Depends(get_db), user: User = Depends(current_user)):
    style = db.get(Style, style_id)
    if not style or style.company_id != company_id:
        raise HTTPException(404, "Modelo não encontrado")
    require_resource_write(db, user, company_id, "subcontract_services")
    seen_types: set[str] = set()
    for index, item in enumerate(payload, start=1):
        if item.step_type == "subcontract":
            service = db.get(SubcontractService, item.subcontract_service_id) if item.subcontract_service_id else None
            if not service or service.company_id != company_id:
                raise HTTPException(422, f"Serviço inválido no passo {index}")
        elif item.step_type in seen_types:
            raise HTTPException(422, f"Só pode haver um passo de \"{item.step_type}\" na sequência")
        else:
            seen_types.add(item.step_type)
    existing = (
        db.query(ProductionRouteStep)
        .filter_by(style_id=style_id)
        .order_by(ProductionRouteStep.sequence)
        .all()
    )
    for step in existing:
        db.delete(step)
    db.flush()
    for index, item in enumerate(payload, start=1):
        db.add(ProductionRouteStep(
            company_id=company_id,
            style_id=style_id,
            sequence=item.sequence or index * 10,
            step_type=item.step_type,
            subcontract_service_id=item.subcontract_service_id if item.step_type == "subcontract" else None,
            is_required=item.is_required,
            notes=item.notes,
        ))
    db.commit()
    return list_production_route(style_id, company_id, db, user)


@router.get("/production-orders/{order_id}/production-route")
def order_production_route(order_id: int, company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = db.get(ProductionOrder, order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(404, "Ordem não encontrada")
    require_resource_read(db, user, company_id, "subcontract_jobs")
    return build_route_status(db, order)
