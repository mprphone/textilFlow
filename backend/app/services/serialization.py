from datetime import date, datetime

from sqlalchemy.inspection import inspect


def model_to_dict(instance) -> dict:
    data = {}
    for column in inspect(instance).mapper.column_attrs:
        value = getattr(instance, column.key)
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        data[column.key] = value
    return data
