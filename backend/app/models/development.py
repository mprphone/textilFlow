from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..db import Base
from .base import TimestampMixin


class Development(Base, TimestampMixin):
    __tablename__ = "developments"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    style_id = Column(Integer, ForeignKey("styles.id"), index=True)
    sample_id = Column(Integer, ForeignKey("samples.id"), index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), index=True)
    code = Column(String(80), nullable=False)
    title = Column(String(200), nullable=False)
    owner_name = Column(String(200), nullable=False, default="Por distribuir")
    cover_url = Column(Text)
    images = Column(JSON, default=list, nullable=False)
    request_source = Column(String(40))
    request_group = Column(String(120), index=True)
    requested_quantity = Column(Integer)
    request_notes = Column(Text)
    current_stage = Column(String(50), default="novo", nullable=False, index=True)
    status = Column(String(50), default="active", nullable=False, index=True)
    waiting_reason = Column(Text)
    description = Column(Text)
    due_date = Column(Date)
    estimated_value = Column(Float)
    production_quantity = Column(Integer)
    __table_args__ = (UniqueConstraint("company_id", "code"),)

    customer = relationship("Customer")
    style = relationship("Style")
    sample = relationship("Sample")
    production_order = relationship("ProductionOrder")
    stage_events = relationship("DevelopmentStageEvent", back_populates="development", cascade="all, delete-orphan")
    comments = relationship("DevelopmentComment", back_populates="development", cascade="all, delete-orphan")
    assignees = relationship("DevelopmentAssignee", back_populates="development", cascade="all, delete-orphan")
    tasks = relationship("DevelopmentTask", back_populates="development", cascade="all, delete-orphan")


class DevelopmentStageEvent(Base):
    __tablename__ = "development_stage_events"
    id = Column(Integer, primary_key=True)
    development_id = Column(Integer, ForeignKey("developments.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(50), nullable=False, index=True)
    status = Column(String(30), default="active", nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True))
    note = Column(Text)
    responsible_name = Column(String(200))
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))

    development = relationship("Development", back_populates="stage_events")
    supplier = relationship("Supplier")


class DevelopmentComment(Base, TimestampMixin):
    __tablename__ = "development_comments"
    id = Column(Integer, primary_key=True)
    development_id = Column(Integer, ForeignKey("developments.id", ondelete="CASCADE"), nullable=False, index=True)
    author = Column(String(120), nullable=False)
    body = Column(Text, nullable=False)
    category = Column(String(40), default="nota_interna", nullable=False)

    development = relationship("Development", back_populates="comments")


class DevelopmentAssignee(Base, TimestampMixin):
    __tablename__ = "development_assignees"
    id = Column(Integer, primary_key=True)
    development_id = Column(Integer, ForeignKey("developments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(40), default="parceria", nullable=False)
    __table_args__ = (UniqueConstraint("development_id", "user_id", "role"),)

    development = relationship("Development", back_populates="assignees")
    user = relationship("User")


class DevelopmentTask(Base, TimestampMixin):
    __tablename__ = "development_tasks"
    id = Column(Integer, primary_key=True)
    development_id = Column(Integer, ForeignKey("developments.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(50), nullable=False, index=True)
    status = Column(String(30), default="pending", nullable=False, index=True)
    note = Column(Text)
    due_date = Column(Date)
    responsible_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    completed_at = Column(DateTime(timezone=True))

    development = relationship("Development", back_populates="tasks")
    responsible = relationship("User")
