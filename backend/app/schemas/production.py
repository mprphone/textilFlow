from pydantic import BaseModel, Field


class ProductionEventRequest(BaseModel):
    assignment_id: int
    quantity_good: float = Field(default=0, ge=0)
    quantity_rejected: float = Field(default=0, ge=0)
    duration_minutes: float = Field(default=0, ge=0)
    event_type: str = "output"
    notes: str | None = None
    source: str = "manual"


class StockMovementRequest(BaseModel):
    stock_lot_id: int
    movement_type: str
    quantity: float
    production_order_id: int | None = None
    location_to: str | None = None
    reference: str | None = None
