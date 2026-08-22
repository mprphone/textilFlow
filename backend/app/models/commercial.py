from sqlalchemy import Boolean, Column, Date, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from ..db import Base
from .base import TimestampMixin


class CommercialDocument(Base, TimestampMixin):
    """Documentos comerciais preparados para o Primavera (compras e vendas)."""

    __tablename__ = "commercial_documents"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    doc_type = Column(String(40), nullable=False, index=True)
    doc_no = Column(String(100), nullable=False)
    doc_date = Column(Date)
    status = Column(String(30), default="draft", nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"))
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id"))
    shipment_id = Column(Integer, ForeignKey("shipments.id"))
    converted_from_id = Column(Integer, ForeignKey("commercial_documents.id"))
    currency = Column(String(3), default="EUR", nullable=False)
    total = Column(Float, default=0, nullable=False)
    notes = Column(Text)
    lines = Column(JSON, default=list, nullable=False)
    primavera_kind = Column(String(40))
    primavera_status = Column(String(30), default="pending", nullable=False)
    primavera_queue_id = Column(String(40))
    primavera_remote_id = Column(String(100))
    primavera_error = Column(Text)
    extra = Column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "doc_no"),)
