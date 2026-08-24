from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from ..db import Base
from .base import TimestampMixin


class FinishedGoodsUnit(Base, TimestampMixin):
    """Saldo físico de produto acabado por SKU/lote/local/unidade logística."""

    __tablename__ = "finished_goods_units"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("style_variants.id"), index=True)
    batch_id = Column(Integer, ForeignKey("production_batches.id"), index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), index=True)
    package_code = Column(String(100), nullable=False)
    package_type = Column(String(30), default="box", nullable=False)
    barcode = Column(String(160), nullable=False, unique=True, index=True)
    initial_quantity = Column(Float, default=0, nullable=False)
    quantity = Column(Float, default=0, nullable=False)
    reserved_quantity = Column(Float, default=0, nullable=False)
    unit_cost = Column(Float, default=0, nullable=False)
    status = Column(String(30), default="available", nullable=False, index=True)
    location = Column(String(150))
    packed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "package_code"),)


class ShipmentAllocation(Base, TimestampMixin):
    __tablename__ = "shipment_allocations"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    shipment_line_id = Column(Integer, ForeignKey("shipment_lines.id"), nullable=False, index=True)
    finished_goods_unit_id = Column(Integer, ForeignKey("finished_goods_units.id"), nullable=False, index=True)
    quantity = Column(Float, default=0, nullable=False)
    __table_args__ = (UniqueConstraint("shipment_line_id", "finished_goods_unit_id"),)


class ReworkOrder(Base, TimestampMixin):
    __tablename__ = "rework_orders"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    quality_inspection_id = Column(Integer, ForeignKey("quality_inspections.id"), index=True)
    batch_id = Column(Integer, ForeignKey("production_batches.id"), index=True)
    variant_id = Column(Integer, ForeignKey("style_variants.id"), index=True)
    operation_id = Column(Integer, ForeignKey("operations.id"), index=True)
    assigned_employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    reference = Column(String(100), nullable=False)
    barcode = Column(String(160), nullable=False, unique=True, index=True)
    quantity = Column(Float, default=0, nullable=False)
    completed_quantity = Column(Float, default=0, nullable=False)
    scrap_quantity = Column(Float, default=0, nullable=False)
    status = Column(String(30), default="open", nullable=False, index=True)
    due_date = Column(Date)
    reason = Column(Text)
    resolution_notes = Column(Text)
    __table_args__ = (UniqueConstraint("company_id", "reference"),)


class CustomerClaim(Base, TimestampMixin):
    __tablename__ = "customer_claims"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=False, index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    claim_no = Column(String(100), nullable=False)
    claim_type = Column(String(40), default="quality", nullable=False)
    quantity = Column(Float, default=0, nullable=False)
    status = Column(String(30), default="open", nullable=False, index=True)
    severity = Column(String(20), default="major", nullable=False)
    reason = Column(Text)
    resolution = Column(Text)
    reported_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at = Column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("company_id", "claim_no"),)


class CustomerReturnLine(Base, TimestampMixin):
    __tablename__ = "customer_return_lines"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    customer_claim_id = Column(Integer, ForeignKey("customer_claims.id"), nullable=False, index=True)
    shipment_line_id = Column(Integer, ForeignKey("shipment_lines.id"), nullable=False, index=True)
    shipment_allocation_id = Column(Integer, ForeignKey("shipment_allocations.id"), index=True)
    finished_goods_unit_id = Column(Integer, ForeignKey("finished_goods_units.id"), index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("style_variants.id"), index=True)
    batch_id = Column(Integer, ForeignKey("production_batches.id"), index=True)
    quantity = Column(Float, default=0, nullable=False)
    disposition = Column(String(30), default="quarantine", nullable=False)
    status = Column(String(30), default="received", nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    notes = Column(Text)


class OperationalNotification(Base, TimestampMixin):
    __tablename__ = "operational_notifications"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    operational_alert_id = Column(Integer, ForeignKey("operational_alerts.id"), nullable=False, index=True)
    recipient_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    channel = Column(String(30), default="in_app", nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)
    attempts = Column(Integer, default=0, nullable=False)
    next_attempt_at = Column(DateTime(timezone=True))
    sent_at = Column(DateTime(timezone=True))
    error = Column(Text)
    __table_args__ = (UniqueConstraint("operational_alert_id", "recipient_user_id", "channel"),)


class ProcurementSuggestion(Base, TimestampMixin):
    __tablename__ = "procurement_suggestions"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), index=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), index=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), index=True)
    required_quantity = Column(Float, default=0, nullable=False)
    available_quantity = Column(Float, default=0, nullable=False)
    suggested_quantity = Column(Float, default=0, nullable=False)
    estimated_unit_cost = Column(Float, default=0, nullable=False)
    needed_by = Column(Date)
    status = Column(String(30), default="suggested", nullable=False, index=True)
    fingerprint = Column(String(180), nullable=False)
    notes = Column(Text)
    __table_args__ = (UniqueConstraint("company_id", "fingerprint"),)


class IntegrationReconciliation(Base, TimestampMixin):
    __tablename__ = "integration_reconciliations"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    system = Column(String(30), default="primavera", nullable=False)
    entity_type = Column(String(50), nullable=False)
    local_reference = Column(String(120), nullable=False)
    remote_reference = Column(String(120))
    local_quantity = Column(Float, default=0, nullable=False)
    remote_quantity = Column(Float, default=0, nullable=False)
    local_value = Column(Float, default=0, nullable=False)
    remote_value = Column(Float, default=0, nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    checked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    detail = Column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "system", "entity_type", "local_reference"),)
