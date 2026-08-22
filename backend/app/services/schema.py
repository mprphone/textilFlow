from sqlalchemy import inspect, text

from ..db import engine


COLUMN_MIGRATIONS = (
    ("customers", "payment_term_code", "ALTER TABLE customers ADD COLUMN payment_term_code VARCHAR(30)"),
    ("customers", "postal_code", "ALTER TABLE customers ADD COLUMN postal_code VARCHAR(20)"),
    ("customers", "city", "ALTER TABLE customers ADD COLUMN city VARCHAR(100)"),
    ("customers", "district", "ALTER TABLE customers ADD COLUMN district VARCHAR(80)"),
    ("customers", "country", "ALTER TABLE customers ADD COLUMN country VARCHAR(60)"),
    ("customers", "fax", "ALTER TABLE customers ADD COLUMN fax VARCHAR(60)"),
    ("customers", "currency", "ALTER TABLE customers ADD COLUMN currency VARCHAR(3)"),
    ("customers", "price_list", "ALTER TABLE customers ADD COLUMN price_list VARCHAR(40)"),
    ("customers", "salesperson", "ALTER TABLE customers ADD COLUMN salesperson VARCHAR(80)"),
    ("customers", "credit_limit", "ALTER TABLE customers ADD COLUMN credit_limit FLOAT"),
    ("customers", "notes", "ALTER TABLE customers ADD COLUMN notes TEXT"),
    ("customers", "sync_status", "ALTER TABLE customers ADD COLUMN sync_status VARCHAR(30)"),
    ("suppliers", "address", "ALTER TABLE suppliers ADD COLUMN address TEXT"),
    ("suppliers", "postal_code", "ALTER TABLE suppliers ADD COLUMN postal_code VARCHAR(20)"),
    ("suppliers", "city", "ALTER TABLE suppliers ADD COLUMN city VARCHAR(100)"),
    ("suppliers", "country", "ALTER TABLE suppliers ADD COLUMN country VARCHAR(60)"),
    ("suppliers", "fax", "ALTER TABLE suppliers ADD COLUMN fax VARCHAR(60)"),
    ("suppliers", "contact_name", "ALTER TABLE suppliers ADD COLUMN contact_name VARCHAR(150)"),
    ("suppliers", "payment_terms", "ALTER TABLE suppliers ADD COLUMN payment_terms VARCHAR(100)"),
    ("suppliers", "payment_term_code", "ALTER TABLE suppliers ADD COLUMN payment_term_code VARCHAR(30)"),
    ("suppliers", "currency", "ALTER TABLE suppliers ADD COLUMN currency VARCHAR(3)"),
    ("suppliers", "iban", "ALTER TABLE suppliers ADD COLUMN iban VARCHAR(50)"),
    ("suppliers", "notes", "ALTER TABLE suppliers ADD COLUMN notes TEXT"),
    ("suppliers", "sync_status", "ALTER TABLE suppliers ADD COLUMN sync_status VARCHAR(30)"),
    ("materials", "last_cost", "ALTER TABLE materials ADD COLUMN last_cost FLOAT DEFAULT 0"),
    ("materials", "barcode", "ALTER TABLE materials ADD COLUMN barcode VARCHAR(80)"),
    ("materials", "family", "ALTER TABLE materials ADD COLUMN family VARCHAR(40)"),
    ("materials", "subfamily", "ALTER TABLE materials ADD COLUMN subfamily VARCHAR(40)"),
    ("materials", "brand", "ALTER TABLE materials ADD COLUMN brand VARCHAR(80)"),
    ("materials", "vat_code", "ALTER TABLE materials ADD COLUMN vat_code VARCHAR(20)"),
    ("materials", "warehouse", "ALTER TABLE materials ADD COLUMN warehouse VARCHAR(40)"),
    ("materials", "item_type", "ALTER TABLE materials ADD COLUMN item_type VARCHAR(20)"),
    ("materials", "primavera_id", "ALTER TABLE materials ADD COLUMN primavera_id VARCHAR(100)"),
    ("materials", "sync_status", "ALTER TABLE materials ADD COLUMN sync_status VARCHAR(30)"),
    ("employees", "monthly_salary", "ALTER TABLE employees ADD COLUMN monthly_salary FLOAT DEFAULT 0"),
    ("production_lines", "target_pcs_hour", "ALTER TABLE production_lines ADD COLUMN target_pcs_hour FLOAT DEFAULT 0"),
    ("suppliers", "weekly_capacity", "ALTER TABLE suppliers ADD COLUMN weekly_capacity FLOAT DEFAULT 0"),
    ("suppliers", "piece_cost", "ALTER TABLE suppliers ADD COLUMN piece_cost FLOAT DEFAULT 0"),
    ("purchase_orders", "production_order_id", "ALTER TABLE purchase_orders ADD COLUMN production_order_id INTEGER"),
    ("subcontract_jobs", "chain_step_sequence", "ALTER TABLE subcontract_jobs ADD COLUMN chain_step_sequence INTEGER"),
    ("production_lines", "wip_limit", "ALTER TABLE production_lines ADD COLUMN wip_limit INTEGER DEFAULT 0"),
    ("production_lines", "kanban_pull_enabled", "ALTER TABLE production_lines ADD COLUMN kanban_pull_enabled BOOLEAN DEFAULT 0"),
    ("production_batches", "kanban_status", "ALTER TABLE production_batches ADD COLUMN kanban_status VARCHAR(30) DEFAULT 'waiting'"),
    ("production_batches", "sewing_line_id", "ALTER TABLE production_batches ADD COLUMN sewing_line_id INTEGER"),
)


def _add_column(connection, table: str, column: str, ddl: str) -> None:
    inspector = inspect(connection)
    if table not in inspector.get_table_names():
        return
    names = {item["name"] for item in inspector.get_columns(table)}
    if column in names:
        return
    dialect = connection.dialect.name
    statement = ddl
    if dialect == "postgresql" and " JSON " in ddl:
        statement = ddl.replace(" JSON ", " JSONB ")
    connection.execute(text(statement))


def _rename_column(connection, table: str, old_name: str, new_name: str) -> None:
    inspector = inspect(connection)
    if table not in inspector.get_table_names():
        return
    names = {item["name"] for item in inspector.get_columns(table)}
    if old_name not in names or new_name in names:
        return
    dialect = connection.dialect.name
    if dialect == "postgresql":
        statement = f'ALTER TABLE "{table}" RENAME COLUMN "{old_name}" TO "{new_name}"'
    elif dialect == "mssql":
        statement = f"EXEC sp_rename '{table}.{old_name}', '{new_name}', 'COLUMN'"
    else:
        statement = f"ALTER TABLE {table} RENAME COLUMN {old_name} TO {new_name}"
    connection.execute(text(statement))


def ensure_schema() -> None:
    inspector = inspect(engine)
    if "companies" not in inspector.get_table_names():
        return
    with engine.begin() as connection:
        _rename_column(connection, "purchase_orders", "purchase_order_id", "production_order_id")
        _add_column(connection, "companies", "settings", "ALTER TABLE companies ADD COLUMN settings JSON DEFAULT '{}'")
        if "users" in inspector.get_table_names():
            dialect = connection.dialect.name
            default = "false" if dialect == "postgresql" else "0"
            _add_column(
                connection, "users", "must_change_password",
                f"ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT {default} NOT NULL",
            )
        for table, column, ddl in COLUMN_MIGRATIONS:
            _add_column(connection, table, column, ddl)
