from pydantic import BaseModel, Field, field_validator


class ProductionEventRequest(BaseModel):
    assignment_id: int
    quantity_good: float = Field(default=0, ge=0)
    quantity_rejected: float = Field(default=0, ge=0)
    duration_minutes: float = Field(default=0, ge=0)
    event_type: str = "output"
    notes: str | None = None
    source: str = "manual"
    allow_overage: bool = False


class ProductionRouteStepIn(BaseModel):
    sequence: int = 10
    step_type: str = "subcontract"
    subcontract_service_id: int | None = None
    is_required: bool = True
    notes: str | None = None

    @field_validator("step_type")
    @classmethod
    def _valid_type(cls, value: str) -> str:
        if value not in {"cutting", "sewing", "subcontract"}:
            raise ValueError("Tipo de passo inválido")
        return value


class StockMovementRequest(BaseModel):
    stock_lot_id: int
    movement_type: str
    quantity: float
    production_order_id: int | None = None
    location_to: str | None = None
    reference: str | None = None
