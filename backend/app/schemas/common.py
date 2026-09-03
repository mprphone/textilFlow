from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Page(BaseModel):
    items: list[Any]
    total: int
    offset: int
    limit: int


class CrudPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    company_id: int | None = None


class UserWrite(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str | None = Field(default=None, min_length=1, max_length=100)
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = None
    password: str | None = Field(default=None, max_length=200)
    role: str | None = None
    active: bool | None = None
    company_ids: list[int] | None = None
    permissions: list[str] | None = None


class UserCreate(UserWrite):
    username: str = Field(min_length=1, max_length=100)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class PrimaveraConfigIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool | None = None
    base_url: str | None = None
    token_url: str | None = None
    erp_company: str | None = None
    instance: str | None = None
    line: str | None = None
    username: str | None = None
    password: str | None = None
    verify_ssl: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=120)
    sales_doc_type: str | None = None
    sales_series: str | None = None
    delivery_doc_type: str | None = None
    delivery_series: str | None = None
    warehouse: str | None = None
    currency: str | None = None


class InvoiceQueueIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    customer_code: str = Field(min_length=1)
    reference: str = ""
    lines: list[dict] = Field(default_factory=list)


class AssistantQuery(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class SyncMastersIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    resources: list[str] | None = None
