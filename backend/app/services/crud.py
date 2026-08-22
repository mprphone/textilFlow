from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, inspect

from .registry import RESOURCE_MODELS


PROTECTED_FIELDS = {"id", "created_at", "updated_at"}


def resource_model(resource: str):
    model = RESOURCE_MODELS.get(resource)
    if not model:
        raise HTTPException(404, "Recurso desconhecido")
    return model


def coerce_value(column, value):
    if value in ("", None):
        return None if column.nullable else value
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(column.type, Date) and isinstance(value, str):
        return date.fromisoformat(value[:10])
    if isinstance(column.type, Boolean) and not isinstance(value, bool):
        return str(value).lower() in {"1", "true", "yes", "sim"}
    if isinstance(column.type, Integer) and not isinstance(value, int):
        return int(value)
    if isinstance(column.type, (Float, Numeric)) and not isinstance(value, (int, float)):
        return float(value)
    return value


def apply_payload(instance, payload: dict, *, company_id: int | None = None):
    columns = {column.key: column for column in inspect(type(instance)).columns}
    for key, value in payload.items():
        if key in PROTECTED_FIELDS or key not in columns:
            continue
        if key == "company_id" and company_id is not None:
            continue
        setattr(instance, key, coerce_value(columns[key], value))
    if company_id is not None and "company_id" in columns:
        instance.company_id = company_id
    return instance
