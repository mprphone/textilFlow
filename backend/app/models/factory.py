from sqlalchemy import Boolean, Column, Date, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from ..db import Base
from .base import TimestampMixin


class Facility(Base, TimestampMixin):
    __tablename__ = "facilities"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(40), nullable=False)
    name = Column(String(150), nullable=False)
    address = Column(Text)
    facility_type = Column(String(40), default="factory", nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class Department(Base, TimestampMixin):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    facility_id = Column(Integer, ForeignKey("facilities.id"))
    code = Column(String(40), nullable=False)
    name = Column(String(150), nullable=False)
    cost_center = Column(String(60))
    hourly_overhead = Column(Float, default=0, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class ProductionLine(Base, TimestampMixin):
    __tablename__ = "production_lines"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"))
    code = Column(String(40), nullable=False)
    name = Column(String(150), nullable=False)
    production_mode = Column(String(30), default="line", nullable=False)
    capacity_minutes_day = Column(Float, default=0, nullable=False)
    target_pcs_hour = Column(Float, default=0, nullable=False)
    target_efficiency = Column(Float, default=85, nullable=False)
    wip_limit = Column(Integer, default=0, nullable=False)
    kanban_pull_enabled = Column(Boolean, default=False, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class SkillType(Base, TimestampMixin):
    __tablename__ = "skill_types"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(40), nullable=False)
    name = Column(String(160), nullable=False)
    machine_type = Column(String(100))
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class MachineType(Base, TimestampMixin):
    __tablename__ = "machine_types"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(40), nullable=False)
    name = Column(String(160), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"))
    line_id = Column(Integer, ForeignKey("production_lines.id"))
    code = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    job_title = Column(String(100))
    monthly_salary = Column(Float, default=0, nullable=False)
    hourly_cost = Column(Float, default=0, nullable=False)
    weekly_hours = Column(Float, default=40, nullable=False)
    skills = Column(JSON, default=list, nullable=False)
    badge_code = Column(String(100))
    custom_data = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class Machine(Base, TimestampMixin):
    __tablename__ = "machines"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"))
    line_id = Column(Integer, ForeignKey("production_lines.id"))
    code = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    machine_type = Column(String(100), nullable=False)
    manufacturer = Column(String(100))
    model = Column(String(100))
    serial_no = Column(String(100))
    hourly_cost = Column(Float, default=0, nullable=False)
    target_units_hour = Column(Float, default=0, nullable=False)
    status = Column(String(30), default="available", nullable=False)
    next_maintenance = Column(Date)
    iot_identifier = Column(String(120))
    custom_data = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)
