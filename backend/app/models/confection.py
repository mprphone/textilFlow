from sqlalchemy import Boolean, Column, Date, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from ..db import Base
from .base import TimestampMixin


class WorkShift(Base, TimestampMixin):
    __tablename__ = "work_shifts"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(40), nullable=False)
    name = Column(String(120), nullable=False)
    start_time = Column(String(5), default="08:00", nullable=False)
    end_time = Column(String(5), default="17:00", nullable=False)
    minutes_day = Column(Float, default=480, nullable=False)
    break_minutes = Column(Float, default=30, nullable=False)
    weekdays = Column(JSON, default=lambda: [1, 2, 3, 4, 5], nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class CapacityDay(Base, TimestampMixin):
    __tablename__ = "capacity_days"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    line_id = Column(Integer, ForeignKey("production_lines.id"), nullable=False, index=True)
    shift_id = Column(Integer, ForeignKey("work_shifts.id"), nullable=True)
    work_date = Column(Date, nullable=False, index=True)
    scheduled_employees = Column(Float, default=0, nullable=False)
    absent_employees = Column(Float, default=0, nullable=False)
    minutes_per_employee = Column(Float, default=480, nullable=False)
    break_minutes = Column(Float, default=30, nullable=False)
    setup_minutes = Column(Float, default=0, nullable=False)
    maintenance_minutes = Column(Float, default=0, nullable=False)
    efficiency_pct = Column(Float, default=85, nullable=False)
    locked = Column(Boolean, default=False, nullable=False)
    notes = Column(Text)
    __table_args__ = (UniqueConstraint("company_id", "line_id", "shift_id", "work_date"),)


class CapacityEvent(Base, TimestampMixin):
    __tablename__ = "capacity_events"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    event_date = Column(Date, nullable=False, index=True)
    line_id = Column(Integer, ForeignKey("production_lines.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=True)
    event_type = Column(String(40), nullable=False)
    description = Column(String(200), nullable=False)
    minutes_delta = Column(Float, default=0, nullable=False)
    status = Column(String(30), default="confirmed", nullable=False)
    notes = Column(Text)


class EmployeeSkill(Base, TimestampMixin):
    __tablename__ = "employee_skills"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    operation_id = Column(Integer, ForeignKey("operations.id"), nullable=True)
    skill_code = Column(String(80), nullable=False)
    skill_name = Column(String(160), nullable=False)
    machine_type = Column(String(100))
    proficiency_level = Column(Integer, default=3, nullable=False)
    efficiency_pct = Column(Float, default=85, nullable=False)
    certified_until = Column(Date)
    preferred = Column(Boolean, default=False, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text)
    __table_args__ = (UniqueConstraint("company_id", "employee_id", "skill_code"),)


class SewingPlan(Base, TimestampMixin):
    __tablename__ = "sewing_plans"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=True, index=True)
    style_id = Column(Integer, ForeignKey("styles.id"), nullable=True)
    line_id = Column(Integer, ForeignKey("production_lines.id"), nullable=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    source_type = Column(String(40), default="confirmed", nullable=False)
    allocation_type = Column(String(30), default="internal", nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    quantity = Column(Float, default=0, nullable=False)
    sam_minutes = Column(Float, default=0, nullable=False)
    efficiency_pct = Column(Float, default=85, nullable=False)
    required_minutes = Column(Float, default=0, nullable=False)
    probability_pct = Column(Float, default=100, nullable=False)
    priority = Column(Integer, default=3, nullable=False)
    status = Column(String(30), default="planned", nullable=False)
    notes = Column(Text)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class ExternalCapacity(Base, TimestampMixin):
    __tablename__ = "external_capacities"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    week_start = Column(Date, nullable=False, index=True)
    capacity_units = Column(Float, default=0, nullable=False)
    reserved_units = Column(Float, default=0, nullable=False)
    unit_cost = Column(Float, default=0, nullable=False)
    lead_time_days = Column(Integer, default=0, nullable=False)
    reliability_pct = Column(Float, default=85, nullable=False)
    status = Column(String(30), default="available", nullable=False)
    notes = Column(Text)
    __table_args__ = (UniqueConstraint("company_id", "supplier_id", "week_start"),)
