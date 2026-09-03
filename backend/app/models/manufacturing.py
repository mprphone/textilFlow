from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from ..db import Base
from .base import TimestampMixin


class SalesOrder(Base, TimestampMixin):
    __tablename__ = "sales_orders"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    order_no = Column(String(100), nullable=False)
    customer_po = Column(String(100))
    order_date = Column(Date)
    delivery_date = Column(Date)
    status = Column(String(40), default="confirmed", nullable=False)
    currency = Column(String(3), default="EUR", nullable=False)
    notes = Column(Text)
    custom_data = Column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "order_no"),)


class SalesOrderLine(Base, TimestampMixin):
    __tablename__ = "sales_order_lines"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=False, index=True)
    style_id = Column(Integer, ForeignKey("styles.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("style_variants.id"))
    description = Column(String(255))
    quantity = Column(Float, default=0, nullable=False)
    unit_price = Column(Float, default=0, nullable=False)
    delivery_date = Column(Date)


class ProductionOrder(Base, TimestampMixin):
    __tablename__ = "production_orders"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    sales_order_line_id = Column(Integer, ForeignKey("sales_order_lines.id"))
    style_id = Column(Integer, ForeignKey("styles.id"), nullable=False)
    line_id = Column(Integer, ForeignKey("production_lines.id"))
    order_no = Column(String(100), nullable=False)
    quantity = Column(Float, default=0, nullable=False)
    completed_quantity = Column(Float, default=0, nullable=False)
    rejected_quantity = Column(Float, default=0, nullable=False)
    planned_start = Column(Date)
    planned_end = Column(Date)
    actual_start = Column(DateTime(timezone=True))
    actual_end = Column(DateTime(timezone=True))
    status = Column(String(40), default="planned", nullable=False)
    priority = Column(Integer, default=3, nullable=False)
    current_stage = Column(String(80), default="planning", nullable=False)
    current_location = Column(String(150))
    custom_data = Column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "order_no"),)


class ProposalProductionRelease(Base, TimestampMixin):
    """Registo imutavel da passagem de uma proposta aceite para producao.

    A restricao por ficha de custo torna o comando idempotente mesmo quando o
    utilizador repete o clique ou o cliente HTTP repete o pedido.
    """

    __tablename__ = "proposal_production_releases"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    cost_sheet_id = Column(Integer, ForeignKey("cost_sheets.id"), nullable=False, unique=True, index=True)
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id"), index=True)
    sales_order_line_id = Column(Integer, ForeignKey("sales_order_lines.id"), index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), index=True)
    idempotency_key = Column(String(120), nullable=False)
    quantity = Column(Float, nullable=False)
    reserve_stock = Column(Boolean, default=True, nullable=False)
    released_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    released_by = Column(Integer, ForeignKey("users.id"))
    request_snapshot = Column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "idempotency_key"),)


class ProductionMaterialRequirement(Base, TimestampMixin):
    """Necessidade de material congelada no momento em que a OF e criada."""

    __tablename__ = "production_material_requirements"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    release_id = Column(Integer, ForeignKey("proposal_production_releases.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    cost_line_id = Column(Integer, ForeignKey("cost_lines.id"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id"), index=True)
    description = Column(String(200), nullable=False)
    material_category = Column(String(80))
    unit = Column(String(20), nullable=False)
    unit_required = Column(Float, default=0, nullable=False)
    required_quantity = Column(Float, default=0, nullable=False)
    available_quantity = Column(Float, default=0, nullable=False)
    shortage_quantity = Column(Float, default=0, nullable=False)
    reserved_quantity = Column(Float, default=0, nullable=False)
    average_unit_cost = Column(Float, default=0, nullable=False)
    real_unit_cost = Column(Float, default=0, nullable=False)
    estimated_amount = Column(Float, default=0, nullable=False)
    lots = Column(JSON, default=list, nullable=False)
    status = Column(String(30), default="planned", nullable=False)
    __table_args__ = (UniqueConstraint("production_order_id", "cost_line_id"),)


class ProductionOrderVariant(Base, TimestampMixin):
    """Grelha cor×tamanho de uma OF, gravada no lançamento da proposta."""

    __tablename__ = "production_order_variants"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("style_variants.id"), nullable=False, index=True)
    quantity = Column(Float, default=0, nullable=False)
    unit_price = Column(Float)
    __table_args__ = (UniqueConstraint("production_order_id", "variant_id"),)


class SequenceCounter(Base, TimestampMixin):
    """Contador atomico por empresa+chave, usado para numerar documentos (ex.: DIST-.., EXT-..)."""

    __tablename__ = "sequence_counters"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    key = Column(String(120), nullable=False)
    value = Column(Integer, default=0, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "key"),)


class ProductionBatch(Base, TimestampMixin):
    __tablename__ = "production_batches"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    sewing_line_id = Column(Integer, ForeignKey("production_lines.id"), index=True)
    variant_id = Column(Integer, ForeignKey("style_variants.id"), index=True)
    source_cutting_job_id = Column(Integer, ForeignKey("cutting_jobs.id"), index=True)
    batch_no = Column(String(100), nullable=False)
    color = Column(String(100))
    size = Column(String(30))
    quantity = Column(Float, default=0, nullable=False)
    completed_quantity = Column(Float, default=0, nullable=False)
    current_operation_id = Column(Integer, ForeignKey("operations.id"))
    current_location = Column(String(150))
    status = Column(String(40), default="waiting", nullable=False)
    kanban_status = Column(String(30), default="waiting", nullable=False)
    barcode = Column(String(120))
    __table_args__ = (UniqueConstraint("company_id", "batch_no"),)


class WorkAssignment(Base, TimestampMixin):
    __tablename__ = "work_assignments"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("production_batches.id"))
    product_operation_id = Column(Integer, ForeignKey("product_operations.id"))
    operation_id = Column(Integer, ForeignKey("operations.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    machine_id = Column(Integer, ForeignKey("machines.id"))
    line_id = Column(Integer, ForeignKey("production_lines.id"))
    planned_quantity = Column(Float, default=0, nullable=False)
    completed_quantity = Column(Float, default=0, nullable=False)
    rejected_quantity = Column(Float, default=0, nullable=False)
    standard_minutes = Column(Float, default=0, nullable=False)
    actual_minutes = Column(Float, default=0, nullable=False)
    planned_start = Column(DateTime(timezone=True))
    planned_end = Column(DateTime(timezone=True))
    status = Column(String(30), default="queued", nullable=False)


class ProductionEvent(Base):
    __tablename__ = "production_events"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    assignment_id = Column(Integer, ForeignKey("work_assignments.id"), index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("production_batches.id"))
    variant_id = Column(Integer, ForeignKey("style_variants.id"), index=True)
    operation_id = Column(Integer, ForeignKey("operations.id"))
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), index=True)
    line_id = Column(Integer, ForeignKey("production_lines.id"), index=True)
    event_type = Column(String(30), default="output", nullable=False)
    event_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    duration_minutes = Column(Float, default=0, nullable=False)
    quantity_good = Column(Float, default=0, nullable=False)
    quantity_rejected = Column(Float, default=0, nullable=False)
    labor_cost = Column(Float, default=0, nullable=False)
    machine_cost = Column(Float, default=0, nullable=False)
    energy_cost = Column(Float, default=0, nullable=False)
    consumables_cost = Column(Float, default=0, nullable=False)
    setup_cost = Column(Float, default=0, nullable=False)
    notes = Column(Text)
    source = Column(String(30), default="manual", nullable=False)


class DowntimeEvent(Base, TimestampMixin):
    __tablename__ = "downtime_events"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"))
    employee_id = Column(Integer, ForeignKey("employees.id"))
    line_id = Column(Integer, ForeignKey("production_lines.id"))
    production_order_id = Column(Integer, ForeignKey("production_orders.id"))
    reason_code = Column(String(60), nullable=False)
    reason = Column(String(200), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True))
    duration_minutes = Column(Float, default=0, nullable=False)
    notes = Column(Text)


class CuttingJob(Base, TimestampMixin):
    __tablename__ = "cutting_jobs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("production_batches.id"))
    cutter_employee_id = Column(Integer, ForeignKey("employees.id"))
    machine_id = Column(Integer, ForeignKey("machines.id"))
    marker_code = Column(String(100))
    fabric_lot = Column(String(100))
    layers = Column(Integer, default=0, nullable=False)
    planned_pieces = Column(Float, default=0, nullable=False)
    good_pieces = Column(Float, default=0, nullable=False)
    rejected_pieces = Column(Float, default=0, nullable=False)
    planned_fabric = Column(Float, default=0, nullable=False)
    actual_fabric = Column(Float, default=0, nullable=False)
    waste_pct = Column(Float, default=0, nullable=False)
    duration_minutes = Column(Float, default=0, nullable=False)
    labor_cost = Column(Float, default=0, nullable=False)
    machine_cost = Column(Float, default=0, nullable=False)
    status = Column(String(30), default="planned", nullable=False)
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
