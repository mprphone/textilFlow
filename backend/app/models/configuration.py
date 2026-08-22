from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.sql import func

from ..db import Base
from .base import TimestampMixin


class FieldDefinition(Base, TimestampMixin):
    __tablename__ = "field_definitions"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    entity_type = Column(String(60), nullable=False, index=True)
    field_key = Column(String(80), nullable=False)
    label = Column(String(150), nullable=False)
    data_type = Column(String(30), default="text", nullable=False)
    required = Column(Boolean, default=False, nullable=False)
    options = Column(JSON, default=list, nullable=False)
    default_value = Column(JSON)
    section = Column(String(100), default="Geral", nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "entity_type", "field_key", "version"),)


class FormTemplate(Base, TimestampMixin):
    __tablename__ = "form_templates"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    entity_type = Column(String(60), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    schema = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "entity_type", "name", "version"),)


class WorkflowDefinition(Base, TimestampMixin):
    __tablename__ = "workflow_definitions"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    entity_type = Column(String(60), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    stages = Column(JSON, default=list, nullable=False)
    active = Column(Boolean, default=True, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    entity = Column(String(100), nullable=False)
    entity_id = Column(String(100))
    action = Column(String(50), nullable=False)
    payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
