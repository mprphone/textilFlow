from sqlalchemy import Boolean, Column, Date, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from ..db import Base
from .base import TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    tax_id = Column(String(40))
    email = Column(String(200))
    phone = Column(String(60))
    address = Column(Text)
    payment_terms = Column(String(100))
    payment_term_code = Column(String(30))
    postal_code = Column(String(20))
    city = Column(String(100))
    district = Column(String(80))
    country = Column(String(60), default="PT")
    fax = Column(String(60))
    currency = Column(String(3), default="EUR")
    price_list = Column(String(40))
    salesperson = Column(String(80))
    credit_limit = Column(Float)
    notes = Column(Text)
    primavera_id = Column(String(100))
    sync_status = Column(String(30), default="local")
    custom_data = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    supplier_type = Column(String(50), default="general", nullable=False)
    tax_id = Column(String(40))
    email = Column(String(200))
    phone = Column(String(60))
    address = Column(Text)
    postal_code = Column(String(20))
    city = Column(String(100))
    country = Column(String(60), default="PT")
    fax = Column(String(60))
    contact_name = Column(String(150))
    payment_terms = Column(String(100))
    payment_term_code = Column(String(30))
    currency = Column(String(3), default="EUR")
    iban = Column(String(50))
    notes = Column(Text)
    lead_time_days = Column(Integer, default=0, nullable=False)
    weekly_capacity = Column(Float, default=0, nullable=False)
    piece_cost = Column(Float, default=0, nullable=False)
    score = Column(Integer, default=0, nullable=False)
    primavera_id = Column(String(100))
    sync_status = Column(String(30), default="local")
    custom_data = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class Certification(Base, TimestampMixin):
    __tablename__ = "certifications"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    cert_type = Column(String(100), nullable=False)
    certificate_no = Column(String(100))
    issued_date = Column(Date)
    expiry_date = Column(Date)
    document_path = Column(Text)
    status = Column(String(30), default="valid", nullable=False)


class SupplierOccurrence(Base, TimestampMixin):
    """Histórico de relacionamento: reclamações, atrasos e comunicações."""

    __tablename__ = "supplier_occurrences"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    occurred_on = Column(Date, nullable=False)
    kind = Column(String(40), default="comunicacao", nullable=False, index=True)
    subject = Column(String(250), nullable=False)
    description = Column(Text)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), index=True)
    subcontract_job_id = Column(Integer, ForeignKey("subcontract_jobs.id"))
    subcontract_service_id = Column(Integer, ForeignKey("subcontract_services.id"))
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"))
    responsible = Column(String(150))
    status = Column(String(30), default="aberto", nullable=False, index=True)
    priority = Column(String(20), default="normal", nullable=False)
    due_date = Column(Date)
    extra = Column(JSON, default=dict, nullable=False)
    __table_args__ = (
        Index("ix_supplier_occurrences_company_supplier", "company_id", "supplier_id"),
        Index("ix_supplier_occurrences_company_order", "company_id", "production_order_id"),
    )


class PaymentTerm(Base, TimestampMixin):
    """Condições de pagamento (CondPag no Primavera)."""

    __tablename__ = "payment_terms"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name = Column(String(150), nullable=False)
    days = Column(Integer, default=0, nullable=False)
    primavera_id = Column(String(100))
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class Bank(Base, TimestampMixin):
    """Bancos (tabela Bancos / Base/Banks no Primavera)."""

    __tablename__ = "banks"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name = Column(String(150), nullable=False)
    swift = Column(String(20))
    country = Column(String(60), default="PT")
    iban_prefix = Column(String(10))
    primavera_id = Column(String(100))
    sync_status = Column(String(30), default="local")
    notes = Column(Text)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)
