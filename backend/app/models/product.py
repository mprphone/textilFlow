from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from ..db import Base
from .base import TimestampMixin


class ArticleType(Base, TimestampMixin):
    __tablename__ = "article_types"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(150), nullable=False)
    category = Column(String(100))
    default_unit = Column(String(20), default="un", nullable=False)
    template_id = Column(Integer, ForeignKey("form_templates.id"))
    workflow_id = Column(Integer, ForeignKey("workflow_definitions.id"))
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class Style(Base, TimestampMixin):
    __tablename__ = "styles"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    article_type_id = Column(Integer, ForeignKey("article_types.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    reference = Column(String(100), nullable=False)
    description = Column(String(255), nullable=False)
    collection = Column(String(100))
    lifecycle_status = Column(String(50), default="development", nullable=False)
    workflow_stage = Column(String(80), default="concept", nullable=False)
    image_url = Column(Text)
    base_unit = Column(String(20), default="un", nullable=False)
    fabric = Column(String(200))
    composition = Column(String(200))
    gsm = Column(Float)
    color = Column(String(100))
    size_range = Column(String(150))
    technical_version = Column(Integer, default=1, nullable=False)
    template_version = Column(Integer, default=1, nullable=False)
    custom_data = Column(JSON, default=dict, nullable=False)
    approved = Column(Boolean, default=False, nullable=False)
    approved_at = Column(DateTime(timezone=True))
    archived = Column(Boolean, default=False, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "reference"),)


class StyleVariant(Base, TimestampMixin):
    __tablename__ = "style_variants"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    style_id = Column(Integer, ForeignKey("styles.id"), nullable=False, index=True)
    sku = Column(String(120), nullable=False)
    color = Column(String(100))
    size = Column(String(30))
    barcode = Column(String(100))
    custom_data = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "sku"),)


class StyleRevision(Base, TimestampMixin):
    __tablename__ = "style_revisions"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    style_id = Column(Integer, ForeignKey("styles.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    snapshot = Column(JSON, default=dict, nullable=False)
    reason = Column(String(255))
    user_id = Column(Integer, ForeignKey("users.id"))
    __table_args__ = (UniqueConstraint("style_id", "version"),)


TF_TYPE_CHOICES = ("unclassified", "finished", "raw_material", "semi_finished", "accessory", "packaging", "consumable")
TF_TYPE_LABELS = {
    "unclassified": "Não classificado",
    "finished": "Produto acabado",
    "raw_material": "Matéria-prima",
    "semi_finished": "Semiacabado",
    "accessory": "Acessório",
    "packaging": "Embalagem",
    "consumable": "Consumível",
}


class Material(Base, TimestampMixin):
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    code = Column(String(80), nullable=False)
    name = Column(String(200), nullable=False)
    category = Column(String(80), default="fabric", nullable=False)
    tf_type = Column(String(20), default="unclassified", nullable=False)
    unit = Column(String(20), default="kg", nullable=False)
    composition = Column(String(200))
    color = Column(String(100))
    width_m = Column(Float)
    gsm = Column(Float)
    unit_cost = Column(Float, default=0, nullable=False)
    last_cost = Column(Float, default=0, nullable=False)
    barcode = Column(String(80))
    family = Column(String(40))
    subfamily = Column(String(40))
    brand = Column(String(80))
    vat_code = Column(String(20), default="23")
    warehouse = Column(String(40))
    item_type = Column(String(20), default="M")
    primavera_id = Column(String(100))
    sync_status = Column(String(30), default="local")
    minimum_stock = Column(Float, default=0, nullable=False)
    lead_time_days = Column(Integer, default=0, nullable=False)
    custom_data = Column(JSON, default=dict, nullable=False)
    notes = Column(Text)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class BOMItem(Base, TimestampMixin):
    __tablename__ = "bom_items"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    style_id = Column(Integer, ForeignKey("styles.id"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    variant_rule = Column(JSON, default=dict, nullable=False)
    quantity = Column(Float, default=0, nullable=False)
    unit = Column(String(20), nullable=False)
    waste_pct = Column(Float, default=0, nullable=False)
    unit_cost = Column(Float, default=0, nullable=False)
    notes = Column(Text)


class Operation(Base, TimestampMixin):
    __tablename__ = "operations"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(60), nullable=False)
    name = Column(String(200), nullable=False)
    department = Column(String(100))
    machine_type = Column(String(100))
    standard_time_min = Column(Float, default=0, nullable=False)
    cost_per_minute = Column(Float, default=0, nullable=False)
    machine_cost_per_minute = Column(Float, default=0, nullable=False)
    instruction = Column(Text)
    media_url = Column(Text)
    active = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class ProductOperation(Base, TimestampMixin):
    __tablename__ = "product_operations"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    style_id = Column(Integer, ForeignKey("styles.id"), nullable=False, index=True)
    operation_id = Column(Integer, ForeignKey("operations.id"), nullable=False)
    sequence = Column(Integer, default=10, nullable=False)
    smv = Column(Float, default=0, nullable=False)
    target_units_hour = Column(Float, default=0, nullable=False)
    skill_level = Column(String(30), default="standard", nullable=False)
    quality_checkpoint = Column(Boolean, default=False, nullable=False)
    instruction_override = Column(Text)


class Sample(Base, TimestampMixin):
    __tablename__ = "samples"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    style_id = Column(Integer, ForeignKey("styles.id"), nullable=False, index=True)
    sample_type = Column(String(60), nullable=False)
    version = Column(String(30), default="V1", nullable=False)
    status = Column(String(40), default="requested", nullable=False)
    responsible_employee_id = Column(Integer, ForeignKey("employees.id"))
    planned_date = Column(Date)
    completed_date = Column(Date)
    labor_minutes = Column(Float, default=0, nullable=False)
    labor_cost = Column(Float, default=0, nullable=False)
    material_cost = Column(Float, default=0, nullable=False)
    external_cost = Column(Float, default=0, nullable=False)
    total_cost = Column(Float, default=0, nullable=False)
    comments = Column(Text)
    custom_data = Column(JSON, default=dict, nullable=False)
