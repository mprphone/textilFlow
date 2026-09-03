from datetime import date

from pydantic import BaseModel, Field


class CapacityCheckInput(BaseModel):
    company_id: int
    style_id: int
    quantity: float = Field(gt=0)
    requested_date: date


class MapOrderInput(BaseModel):
    client: str = "Cliente"
    article: str = "Artigo"
    quantity: float = Field(gt=0)
    sam_minutes: float = Field(gt=0)
    style_id: int | None = None
    line_key: str | None = None
    start_date: date | None = None
    promised_date: date | None = None
    urgent: bool = False
    extra_hours: bool = False
    source_type: str = "confirmed"


class MapMoveInput(BaseModel):
    plan_id: int
    line_key: str | None = None
    start_date: date | None = None
    extra_hours: bool = False
    action: str = "add"
    from_date: date | None = None
    supplier_id: int | None = None
    day_shares: dict[str, float] | None = None
    fabric_quantity: float | None = None
    override: bool = False


class MapPlanInput(BaseModel):
    plan_id: int
    extra_hours: bool = False
    days: int = 1
    fabric_quantity: float | None = None
    override: bool = False


class MapSimulateInput(BaseModel):
    quantity: float = Field(gt=0)
    sam_minutes: float = Field(default=0, ge=0)
    style_id: int | None = None
    article: str = ""
    promised_date: date | None = None
    extra_hours: bool = False
    convert: bool = False
    client: str = "Cliente"
    line_key: str | None = None


class DailyOutputInput(BaseModel):
    work_date: date
    production_order_id: int
    employee_id: int
    line_id: int | None = None
    quantity_good: float = Field(ge=0)
    quantity_rejected: float = Field(default=0, ge=0)
    hours: float = Field(default=8, gt=0)
    notes: str | None = None


class DailyOutputSizeInput(BaseModel):
    variant_id: int | None = None
    quantity_good: float = Field(gt=0)


class DailyOutputBulkInput(BaseModel):
    work_date: date = Field(default_factory=date.today)
    production_order_id: int
    line_id: int
    outputs: list[DailyOutputSizeInput] = Field(min_length=1)
    notes: str | None = None
