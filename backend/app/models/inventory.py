from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.sql import func

from ..db import Base
from .base import TimestampMixin


class StockLot(Base, TimestampMixin):
    __tablename__ = "stock_lots"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    lot_no = Column(String(100), nullable=False)
    location = Column(String(100))
    quantity = Column(Float, default=0, nullable=False)
    reserved = Column(Float, default=0, nullable=False)
    unit_cost = Column(Float, default=0, nullable=False)
    received_date = Column(Date)
    expiry_date = Column(Date)
    certification_snapshot = Column(JSON, default=dict, nullable=False)
    status = Column(String(30), default="available", nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "material_id", "lot_no"),)


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    stock_lot_id = Column(Integer, ForeignKey("stock_lots.id"), nullable=False)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"))
    movement_type = Column(String(30), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_cost = Column(Float, default=0, nullable=False)
    location_from = Column(String(100))
    location_to = Column(String(100))
    reference = Column(String(150))
    movement_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))


class Warehouse(Base, TimestampMixin):
    """Armazéns (tabela Armazem / Base/Warehouses no Primavera)."""

    __tablename__ = "warehouses"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name = Column(String(150), nullable=False)
    location = Column(String(150))
    primavera_id = Column(String(100))
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class PurchaseOrder(Base, TimestampMixin):
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    order_no = Column(String(100), nullable=False)
    order_date = Column(Date)
    expected_date = Column(Date)
    status = Column(String(30), default="draft", nullable=False)
    total = Column(Float, default=0, nullable=False)
    notes = Column(String(500))
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), index=True)
    __table_args__ = (UniqueConstraint("company_id", "order_no"),)


class PurchaseOrderLine(Base, TimestampMixin):
    __tablename__ = "purchase_order_lines"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    quantity = Column(Float, default=0, nullable=False)
    unit_cost = Column(Float, default=0, nullable=False)
    received_quantity = Column(Float, default=0, nullable=False)
