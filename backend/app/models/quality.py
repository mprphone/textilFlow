from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from ..db import Base
from .base import TimestampMixin


class QualityInspection(Base, TimestampMixin):
    __tablename__ = "quality_inspections"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"))
    batch_id = Column(Integer, ForeignKey("production_batches.id"))
    operation_id = Column(Integer, ForeignKey("operations.id"))
    employee_id = Column(Integer, ForeignKey("employees.id"))
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    inspection_type = Column(String(50), default="inline", nullable=False)
    inspected_quantity = Column(Float, default=0, nullable=False)
    defect_quantity = Column(Float, default=0, nullable=False)
    defect_code = Column(String(100))
    severity = Column(String(30), default="minor", nullable=False)
    result = Column(String(30), default="pending", nullable=False)
    notes = Column(Text)
    photos = Column(JSON, default=list, nullable=False)


class Shipment(Base, TimestampMixin):
    __tablename__ = "shipments"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=False)
    shipment_no = Column(String(100), nullable=False)
    carrier = Column(String(150))
    tracking_no = Column(String(150))
    destination = Column(Text)
    quantity = Column(Float, default=0, nullable=False)
    shipped_at = Column(DateTime(timezone=True))
    status = Column(String(30), default="planned", nullable=False)
    documents = Column(JSON, default=list, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "shipment_no"),)
