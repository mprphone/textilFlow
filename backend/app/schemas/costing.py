from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CostingModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class CostLineInput(CostingModel):
    id: int | None = None
    category: str
    description: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, ge=0)
    unit: str = Field(default="un", min_length=1, max_length=20)
    unit_cost: float = Field(default=0, ge=0)
    source_type: str | None = None
    source_id: int | None = None


class CostSheetCreate(CostingModel):
    company_id: int
    style_id: int
    customer_id: int | None = None
    quote_no: str | None = None
    quantity: float = Field(default=1, gt=0)
    selling_price: float = Field(default=0, ge=0)
    valid_until: date | None = None
    notes: str | None = None
    vat_pct: float = Field(default=23, ge=0, le=100)
    payment_terms: str | None = None
    client_notes: str | None = None
    import_technical_costs: bool = True


class CostSheetSave(CostingModel):
    customer_id: int | None = None
    quote_no: str | None = None
    quantity: float = Field(gt=0)
    selling_price: float = Field(ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    valid_until: date | None = None
    notes: str | None = None
    vat_pct: float = Field(default=23, ge=0, le=100)
    payment_terms: str | None = None
    client_notes: str | None = None
    lines: list[CostLineInput]


class ActualCostInput(CostingModel):
    category: str
    description: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, ge=0)
    unit: str = Field(default="un", min_length=1, max_length=20)
    unit_cost: float = Field(default=0, ge=0)
    occurred_on: date
    reference: str | None = None
    notes: str | None = None


class WizardComponentInput(CostingModel):
    material_id: int | None = None
    operation_id: int | None = None
    subcontract_service_id: int | None = None
    description: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, ge=0)
    unit: str = Field(default="un", min_length=1, max_length=20)
    unit_cost: float = Field(default=0, ge=0)
    waste_pct: float = Field(default=0, ge=0, le=100)
    image_url: str | None = None
    color: str | None = None


class WizardProposalCreate(CostingModel):
    company_id: int
    article_type_id: int
    customer_id: int | None = None
    reference: str | None = None
    description: str = Field(min_length=1, max_length=255)
    quantity: float = Field(gt=0)
    selling_price: float = Field(default=0, ge=0)
    valid_until: date | None = None
    piece_image_url: str | None = None
    color: str | None = None
    notes: str | None = None
    materials: list[WizardComponentInput] = Field(default_factory=list)
    accessories: list[WizardComponentInput] = Field(default_factory=list)
    operations: list[WizardComponentInput] = Field(default_factory=list)
    services: list[WizardComponentInput] = Field(default_factory=list)
    overheads: list[WizardComponentInput] = Field(default_factory=list)


class GradeCell(CostingModel):
    """Uma célula da grelha cor×tamanho: quantidade (e opcionalmente preço) para uma combinação."""

    color: str | None = Field(default=None, max_length=100)
    size: str | None = Field(default=None, max_length=30)
    quantity: float = Field(gt=0)
    unit_price: float | None = Field(default=None, ge=0)


class ProposalReleaseRequest(CostingModel):
    """Dados operacionais necessarios para aceitar e lancar uma proposta."""

    quantity: float | None = Field(default=None, gt=0)
    grade: list[GradeCell] | None = None
    customer_id: int | None = Field(default=None, gt=0)
    order_no: str | None = Field(default=None, max_length=100)
    sales_order_no: str | None = Field(default=None, max_length=100)
    customer_po: str | None = Field(default=None, max_length=100)
    order_date: date | None = None
    delivery_date: date | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    line_id: int | None = Field(default=None, gt=0)
    priority: int = Field(default=3, ge=1, le=5)
    reserve_stock: bool = True
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)
