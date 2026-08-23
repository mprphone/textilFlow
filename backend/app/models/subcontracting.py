from sqlalchemy import Boolean, Column, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint

from ..db import Base
from .base import TimestampMixin


class ServiceStage(Base, TimestampMixin):
    """Etapa de produção configurável (corte, confeção, revista, bordado…).

    Lista aberta por empresa — não um enum fixo no código — para se poder
    acrescentar etapas novas (ex.: passadoria) sem alterar o programa.
    """

    __tablename__ = "service_stages"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(60), nullable=False)
    name = Column(String(120), nullable=False)
    sequence = Column(Integer, default=0, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class SubcontractService(Base, TimestampMixin):
    """Serviço e preço acordado com um fornecedor externo."""

    __tablename__ = "subcontract_services"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    code = Column(String(60), nullable=False)
    name = Column(String(200), nullable=False)
    category = Column(String(60), default="other", nullable=False)
    production_stage_id = Column(Integer, ForeignKey("service_stages.id"), nullable=True, index=True)
    execution_type = Column(String(20), default="external", nullable=False)
    allows_partial_batches = Column(Boolean, default=True, nullable=False)
    description = Column(Text)
    unit = Column(String(20), default="un", nullable=False)
    unit_cost = Column(Float, default=0, nullable=False)
    minimum_quantity = Column(Float, default=0, nullable=False)
    lead_time_days = Column(Integer, default=0, nullable=False)
    quality_score = Column(Float, default=100, nullable=False)
    notes = Column(Text)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "supplier_id", "code"),)


class ProductionRouteStep(Base, TimestampMixin):
    """Passo configuravel da sequencia de producao de um artigo.

    Generaliza o antigo SubcontractChainStep para incluir tambem etapas
    internas (corte, confecao), nao so subcontratos. A ordem entre elas
    e livre por artigo: um artigo pode tingir a malha antes de cortar,
    outro pode confecionar a peca e so depois mandar tingir.
    """

    __tablename__ = "production_route_steps"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    style_id = Column(Integer, ForeignKey("styles.id"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False, default=1)
    step_type = Column(String(20), default="subcontract", nullable=False)
    subcontract_service_id = Column(Integer, ForeignKey("subcontract_services.id"), nullable=True, index=True)
    is_required = Column(Boolean, default=True, nullable=False)
    notes = Column(Text)
    __table_args__ = (UniqueConstraint("style_id", "sequence"),)


class SubcontractJob(Base, TimestampMixin):
    """Envio real a um subcontratado, com custo previsto e custo faturado."""

    __tablename__ = "subcontract_jobs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=True, index=True)
    subcontract_service_id = Column(Integer, ForeignKey("subcontract_services.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    chain_step_sequence = Column(Integer, nullable=True, index=True)
    reference = Column(String(100), nullable=False)
    quantity = Column(Float, default=0, nullable=False)
    unit = Column(String(20), default="un", nullable=False)
    unit_cost = Column(Float, default=0, nullable=False)
    planned_cost = Column(Float, default=0, nullable=False)
    actual_cost = Column(Float, default=0, nullable=False)
    sent_date = Column(Date)
    expected_date = Column(Date)
    received_date = Column(Date)
    status = Column(String(30), default="planned", nullable=False)
    accepted_quantity = Column(Float, default=0, nullable=False)
    rejected_quantity = Column(Float, default=0, nullable=False)
    notes = Column(Text)
    __table_args__ = (UniqueConstraint("company_id", "reference"),)
