from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from ..db import Base
from .base import TimestampMixin


class QualityInspection(Base, TimestampMixin):
    __tablename__ = "quality_inspections"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"))
    batch_id = Column(Integer, ForeignKey("production_batches.id"))
    variant_id = Column(Integer, ForeignKey("style_variants.id"), index=True)
    operation_id = Column(Integer, ForeignKey("operations.id"))
    employee_id = Column(Integer, ForeignKey("employees.id"))
    machine_id = Column(Integer, ForeignKey("machines.id"))
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    inspection_type = Column(String(50), default="inline", nullable=False)
    inspected_quantity = Column(Float, default=0, nullable=False)
    defect_quantity = Column(Float, default=0, nullable=False)
    defect_code = Column(String(100))
    severity = Column(String(30), default="minor", nullable=False)
    result = Column(String(30), default="pending", nullable=False)
    disposition = Column(String(30), default="pending", nullable=False)
    released_quantity = Column(Float, default=0, nullable=False)
    rework_quantity = Column(Float, default=0, nullable=False)
    scrap_quantity = Column(Float, default=0, nullable=False)
    notes = Column(Text)
    photos = Column(JSON, default=list, nullable=False)


class CorrectiveAction(Base, TimestampMixin):
    """Acao corretiva (CAPA) estruturada, ligada a uma inspecao de qualidade."""

    __tablename__ = "corrective_actions"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    quality_inspection_id = Column(Integer, ForeignKey("quality_inspections.id"), nullable=False, index=True)
    responsible_employee_id = Column(Integer, ForeignKey("employees.id"))
    root_cause = Column(Text)
    action = Column(Text)
    due_date = Column(DateTime(timezone=True))
    status = Column(String(20), default="open", nullable=False)
    effectiveness_notes = Column(Text)
    verified_at = Column(DateTime(timezone=True))


class Shipment(Base, TimestampMixin):
    """Packing list e, depois da saída, expedição.

    O mesmo registo acompanha a mercadoria desde a preparação até à
    fatura. Isto permite vários packing lists/expedições para a mesma
    encomenda sem perder a ligação às variantes e unidades logísticas.
    """
    __tablename__ = "shipments"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=False)
    shipment_no = Column(String(100), nullable=False)
    carrier = Column(String(150))
    tracking_no = Column(String(150))
    destination = Column(Text)
    quantity = Column(Float, default=0, nullable=False)
    shipped_at = Column(DateTime(timezone=True))
    status = Column(String(30), default="preparing", nullable=False)
    packing_mode = Column(String(20), default="simple", nullable=False)
    package_count = Column(Integer, default=0, nullable=False)
    net_weight = Column(Float, default=0, nullable=False)
    gross_weight = Column(Float, default=0, nullable=False)
    packing_data = Column(JSON, default=dict, nullable=False)
    closed_at = Column(DateTime(timezone=True))
    vehicle_plate = Column(String(40))
    notes = Column(Text)
    documents = Column(JSON, default=list, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "shipment_no"),)


class ShipmentLine(Base, TimestampMixin):
    """Quantidade de uma OF/linha comercial incluida numa expedicao.

    Uma encomenda pode originar varias expedicoes e a mesma linha pode ser
    repartida por varias delas. O detalhe por OF preserva a rastreabilidade
    entre o que foi produzido, aprovado, embalado e efetivamente enviado.
    """

    __tablename__ = "shipment_lines"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=False, index=True)
    sales_order_line_id = Column(Integer, ForeignKey("sales_order_lines.id"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("style_variants.id"), index=True)
    quantity = Column(Float, default=0, nullable=False)
    __table_args__ = (UniqueConstraint("shipment_id", "production_order_id", "variant_id"),)
