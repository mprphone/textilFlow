from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text

from ..db import Base
from .base import TimestampMixin


class ProcessJob(Base, TimestampMixin):
    """Trabalho interno de um processo de fábrica (tinturaria, tecelagem, etc.)."""

    __tablename__ = "process_jobs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    process_kind = Column(String(40), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), index=True)
    batch_id = Column(Integer, ForeignKey("production_batches.id"))
    line_id = Column(Integer, ForeignKey("production_lines.id"))
    machine_id = Column(Integer, ForeignKey("machines.id"))
    employee_id = Column(Integer, ForeignKey("employees.id"))
    reference = Column(String(100), nullable=False)
    quantity = Column(Float, default=0, nullable=False)
    completed_quantity = Column(Float, default=0, nullable=False)
    rejected_quantity = Column(Float, default=0, nullable=False)
    unit = Column(String(20), default="un", nullable=False)
    status = Column(String(30), default="planned", nullable=False)
    planned_date = Column(Date)
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    notes = Column(Text)
