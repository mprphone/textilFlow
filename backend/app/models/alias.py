from sqlalchemy import Column, Float, ForeignKey, Integer, String, UniqueConstraint

from ..db import Base
from .base import TimestampMixin


class ItemAlias(Base, TimestampMixin):
    """Aprendizagem: o que o fornecedor escreve ↔ artigo TextileFlow."""

    __tablename__ = "item_aliases"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    source_code = Column(String(120), default="", nullable=False)
    source_name = Column(String(255), default="", nullable=False)
    normalized = Column(String(255), default="", nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    hits = Column(Integer, default=1, nullable=False)
    confidence = Column(Float, default=1, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "supplier_id", "source_code", "normalized", "material_id"),)
