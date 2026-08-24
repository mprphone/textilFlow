from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from ..db import Base
from .base import TimestampMixin


class ProductionMovement(Base):
    """Livro imutavel de movimentos de WIP e produto acabado."""

    __tablename__ = "production_movements"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("production_batches.id"), index=True)
    variant_id = Column(Integer, ForeignKey("style_variants.id"), index=True)
    product_operation_id = Column(Integer, ForeignKey("product_operations.id"), index=True)
    quality_inspection_id = Column(Integer, ForeignKey("quality_inspections.id"), index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), index=True)
    finished_goods_unit_id = Column(Integer, ForeignKey("finished_goods_units.id"), index=True)
    rework_order_id = Column(Integer, ForeignKey("rework_orders.id"), index=True)
    customer_return_id = Column(Integer, ForeignKey("customer_return_lines.id"), index=True)
    movement_type = Column(String(40), nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    location_from = Column(String(120))
    location_to = Column(String(120), nullable=False)
    reference = Column(String(160))
    idempotency_key = Column(String(180), unique=True, index=True)
    metadata_json = Column(JSON, default=dict, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))


class BatchGenealogy(Base, TimestampMixin):
    """Aresta de genealogia: split, merge, retrabalho ou substituicao."""

    __tablename__ = "batch_genealogy"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    parent_batch_id = Column(Integer, ForeignKey("production_batches.id"), nullable=False, index=True)
    child_batch_id = Column(Integer, ForeignKey("production_batches.id"), nullable=False, index=True)
    relation_type = Column(String(30), default="split", nullable=False)
    quantity = Column(Float, default=0, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    notes = Column(Text)
    __table_args__ = (UniqueConstraint("parent_batch_id", "child_batch_id", "relation_type"),)


class OperationalAlert(Base, TimestampMixin):
    """Excecao operacional persistente e acionavel, reconstruida idempotentemente."""

    __tablename__ = "operational_alerts"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), index=True)
    code = Column(String(80), nullable=False)
    severity = Column(String(20), default="info", nullable=False, index=True)
    title = Column(String(200), nullable=False)
    detail = Column(Text)
    action_label = Column(String(120))
    action_route = Column(String(120))
    status = Column(String(20), default="open", nullable=False, index=True)
    fingerprint = Column(String(200), nullable=False)
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True))
    seen_at = Column(DateTime(timezone=True))
    seen_by = Column(Integer, ForeignKey("users.id"))
    metadata_json = Column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "fingerprint"),)
