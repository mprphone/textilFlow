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
    ("operations", "machine_cost_per_minute", "ALTER TABLE operations ADD COLUMN machine_cost_per_minute FLOAT DEFAULT 0"),
    ("quality_inspections", "machine_id", "ALTER TABLE quality_inspections ADD COLUMN machine_id INTEGER"),
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
    if dialect == "postgresql":
        if " JSON " in statement:
            statement = statement.replace(" JSON ", " JSONB ")
        # Postgres rejeita DEFAULT 0 em colunas BOOLEAN (SQLite aceita).
        statement = statement.replace(" BOOLEAN DEFAULT 0", " BOOLEAN DEFAULT false")
        statement = statement.replace(" BOOLEAN DEFAULT 1", " BOOLEAN DEFAULT true")
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


def _migrate_subcontract_chain_to_route(connection) -> None:
    """Copia SubcontractChainStep (so externos) para ProductionRouteStep (interno+externo).

    Aditivo e idempotente: so copia passos cujo (style_id, sequence) ainda nao
    existe no destino. A tabela antiga fica intacta, nao e apagada. Para
    preservar o comportamento antigo tal e qual (corte sempre obrigatorio
    antes de qualquer subcontrato, confecao sempre no fim), acrescenta um
    passo sintetico de corte no inicio e de confecao no fim de cada artigo
    migrado - o utilizador pode depois reordena-los livremente na UI.
    """
    inspector = inspect(connection)
    tables = inspector.get_table_names()
    if "subcontract_chain_steps" not in tables or "production_route_steps" not in tables:
        return
    existing_seq = {
        (row[0], row[1])
        for row in connection.execute(text("SELECT style_id, sequence FROM production_route_steps"))
    }
    existing_types = {
        (row[0], row[1])
        for row in connection.execute(text("SELECT style_id, step_type FROM production_route_steps"))
    }
    old_rows = connection.execute(text(
        "SELECT company_id, style_id, sequence, subcontract_service_id, is_required, notes "
        "FROM subcontract_chain_steps ORDER BY style_id, sequence"
    )).fetchall()
    by_style: dict[int, list] = {}
    for row in old_rows:
        by_style.setdefault(row[1], []).append(row)

    def insert(company_id, style_id, sequence, step_type, service_id, is_required, notes):
        if (style_id, sequence) in existing_seq:
            return
        connection.execute(
            text(
                "INSERT INTO production_route_steps "
                "(company_id, style_id, sequence, step_type, subcontract_service_id, is_required, notes) "
                "VALUES (:company_id, :style_id, :sequence, :step_type, :service_id, :is_required, :notes)"
            ),
            {
                "company_id": company_id, "style_id": style_id, "sequence": sequence, "step_type": step_type,
                "service_id": service_id, "is_required": is_required, "notes": notes,
            },
        )
        existing_seq.add((style_id, sequence))

    for style_id, rows in by_style.items():
        company_id = rows[0][0]
        if (style_id, "cutting") not in existing_types:
            insert(company_id, style_id, 0, "cutting", None, True, "Migrado automaticamente: o corte era sempre obrigatório antes de qualquer subcontrato.")
            existing_types.add((style_id, "cutting"))
        for _, _, sequence, service_id, is_required, notes in rows:
            insert(company_id, style_id, sequence, "subcontract", service_id, is_required, notes)
        if (style_id, "sewing") not in existing_types:
            max_seq = max(row[2] for row in rows)
            insert(company_id, style_id, max_seq + 10, "sewing", None, True, "Migrado automaticamente: a confeção interna ficava sempre no fim da cadeia antiga.")
            existing_types.add((style_id, "sewing"))


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
        _migrate_subcontract_chain_to_route(connection)
