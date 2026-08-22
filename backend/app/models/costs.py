from sqlalchemy import Column, Date, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from ..db import Base
from .base import TimestampMixin


class CostSheet(Base, TimestampMixin):
    __tablename__ = "cost_sheets"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    style_id = Column(Integer, ForeignKey("styles.id"), nullable=False, index=True)
    version = Column(Integer, default=1, nullable=False)
    status = Column(String(30), default="draft", nullable=False)
    quantity_basis = Column(Float, default=1, nullable=False)
    material_cost = Column(Float, default=0, nullable=False)
    labor_cost = Column(Float, default=0, nullable=False)
    machine_cost = Column(Float, default=0, nullable=False)
    subcontract_cost = Column(Float, default=0, nullable=False)
    overhead_cost = Column(Float, default=0, nullable=False)
    other_cost = Column(Float, default=0, nullable=False)
    total_cost = Column(Float, default=0, nullable=False)
    selling_price = Column(Float, default=0, nullable=False)
    margin_pct = Column(Float, default=0, nullable=False)
    currency = Column(String(3))
    custom_data = Column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("style_id", "version"),)


class CostLine(Base, TimestampMixin):
    __tablename__ = "cost_lines"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    cost_sheet_id = Column(Integer, ForeignKey("cost_sheets.id"), nullable=False, index=True)
    category = Column(String(40), nullable=False)
    description = Column(String(200), nullable=False)
    quantity = Column(Float, default=1, nullable=False)
    unit = Column(String(20), default="un", nullable=False)
    unit_cost = Column(Float, default=0, nullable=False)
    amount = Column(Float, default=0, nullable=False)
    source_type = Column(String(40))
    source_id = Column(Integer)


class OverheadCost(Base, TimestampMixin):
    __tablename__ = "overhead_costs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"))
    category = Column(String(80), nullable=False)
    description = Column(String(200), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    amount = Column(Float, default=0, nullable=False)
    allocation_basis = Column(String(40), default="production_minutes", nullable=False)
    custom_data = Column(JSON, default=dict, nullable=False)


class ExchangeRate(Base, TimestampMixin):
    """Taxa de cambio manual de uma moeda estrangeira para a moeda da empresa
    (Company.currency). Nao e um modulo de tesouraria - apenas o suficiente
    para nao somar valores de moedas diferentes como se fossem iguais."""

    __tablename__ = "exchange_rates"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    currency = Column(String(3), nullable=False)
    rate_to_base = Column(Float, nullable=False)
    effective_date = Column(Date, nullable=False)
    notes = Column(Text)
    __table_args__ = (UniqueConstraint("company_id", "currency", "effective_date"),)


class ActualCostEntry(Base, TimestampMixin):
    """Custo real introduzido por documento quando não nasce do MES ou do stock."""

    __tablename__ = "actual_cost_entries"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    category = Column(String(40), nullable=False)
    description = Column(String(200), nullable=False)
    quantity = Column(Float, default=1, nullable=False)
    unit = Column(String(20), default="un", nullable=False)
    unit_cost = Column(Float, default=0, nullable=False)
    amount = Column(Float, default=0, nullable=False)
    occurred_on = Column(Date, nullable=False)
    reference = Column(String(150))
    notes = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))
