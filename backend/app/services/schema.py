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
    ("materials", "tf_type", "ALTER TABLE materials ADD COLUMN tf_type VARCHAR(20) DEFAULT 'unclassified'"),
    ("materials", "notes", "ALTER TABLE materials ADD COLUMN notes TEXT"),
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
    ("cost_sheets", "currency", "ALTER TABLE cost_sheets ADD COLUMN currency VARCHAR(3)"),
    ("subcontract_services", "production_stage_id", "ALTER TABLE subcontract_services ADD COLUMN production_stage_id INTEGER"),
    ("subcontract_services", "execution_type", "ALTER TABLE subcontract_services ADD COLUMN execution_type VARCHAR(20) DEFAULT 'external'"),
    ("subcontract_services", "allows_partial_batches", "ALTER TABLE subcontract_services ADD COLUMN allows_partial_batches BOOLEAN DEFAULT 1"),
    ("subcontract_services", "description", "ALTER TABLE subcontract_services ADD COLUMN description TEXT"),
    ("shipment_lines", "variant_id", "ALTER TABLE shipment_lines ADD COLUMN variant_id INTEGER REFERENCES style_variants(id)"),
    ("shipments", "packing_mode", "ALTER TABLE shipments ADD COLUMN packing_mode VARCHAR(20) DEFAULT 'simple' NOT NULL"),
    ("shipments", "package_count", "ALTER TABLE shipments ADD COLUMN package_count INTEGER DEFAULT 0 NOT NULL"),
    ("shipments", "net_weight", "ALTER TABLE shipments ADD COLUMN net_weight FLOAT DEFAULT 0 NOT NULL"),
    ("shipments", "gross_weight", "ALTER TABLE shipments ADD COLUMN gross_weight FLOAT DEFAULT 0 NOT NULL"),
    ("shipments", "packing_data", "ALTER TABLE shipments ADD COLUMN packing_data JSON DEFAULT '{}' NOT NULL"),
    ("shipments", "closed_at", "ALTER TABLE shipments ADD COLUMN closed_at TIMESTAMP"),
    ("shipments", "vehicle_plate", "ALTER TABLE shipments ADD COLUMN vehicle_plate VARCHAR(40)"),
    ("shipments", "notes", "ALTER TABLE shipments ADD COLUMN notes TEXT"),
    ("production_batches", "variant_id", "ALTER TABLE production_batches ADD COLUMN variant_id INTEGER REFERENCES style_variants(id)"),
    ("production_batches", "source_cutting_job_id", "ALTER TABLE production_batches ADD COLUMN source_cutting_job_id INTEGER REFERENCES cutting_jobs(id)"),
    ("quality_inspections", "variant_id", "ALTER TABLE quality_inspections ADD COLUMN variant_id INTEGER REFERENCES style_variants(id)"),
    ("quality_inspections", "disposition", "ALTER TABLE quality_inspections ADD COLUMN disposition VARCHAR(30) DEFAULT 'pending' NOT NULL"),
    ("quality_inspections", "released_quantity", "ALTER TABLE quality_inspections ADD COLUMN released_quantity FLOAT DEFAULT 0 NOT NULL"),
    ("quality_inspections", "rework_quantity", "ALTER TABLE quality_inspections ADD COLUMN rework_quantity FLOAT DEFAULT 0 NOT NULL"),
    ("quality_inspections", "scrap_quantity", "ALTER TABLE quality_inspections ADD COLUMN scrap_quantity FLOAT DEFAULT 0 NOT NULL"),
    ("production_movements", "finished_goods_unit_id", "ALTER TABLE production_movements ADD COLUMN finished_goods_unit_id INTEGER REFERENCES finished_goods_units(id)"),
    ("production_movements", "rework_order_id", "ALTER TABLE production_movements ADD COLUMN rework_order_id INTEGER REFERENCES rework_orders(id)"),
    ("production_movements", "customer_return_id", "ALTER TABLE production_movements ADD COLUMN customer_return_id INTEGER REFERENCES customer_return_lines(id)"),
    ("subcontract_jobs", "batch_id", "ALTER TABLE subcontract_jobs ADD COLUMN batch_id INTEGER REFERENCES production_batches(id)"),
    ("subcontract_jobs", "variant_id", "ALTER TABLE subcontract_jobs ADD COLUMN variant_id INTEGER REFERENCES style_variants(id)"),
    ("sewing_plans", "batch_id", "ALTER TABLE sewing_plans ADD COLUMN batch_id INTEGER REFERENCES production_batches(id)"),
    ("sewing_plans", "variant_id", "ALTER TABLE sewing_plans ADD COLUMN variant_id INTEGER REFERENCES style_variants(id)"),
    ("production_events", "energy_cost", "ALTER TABLE production_events ADD COLUMN energy_cost FLOAT DEFAULT 0 NOT NULL"),
    ("production_events", "consumables_cost", "ALTER TABLE production_events ADD COLUMN consumables_cost FLOAT DEFAULT 0 NOT NULL"),
    ("production_events", "setup_cost", "ALTER TABLE production_events ADD COLUMN setup_cost FLOAT DEFAULT 0 NOT NULL"),
    ("production_events", "variant_id", "ALTER TABLE production_events ADD COLUMN variant_id INTEGER REFERENCES style_variants(id)"),
    ("customer_return_lines", "shipment_allocation_id", "ALTER TABLE customer_return_lines ADD COLUMN shipment_allocation_id INTEGER REFERENCES shipment_allocations(id)"),
    ("customer_return_lines", "finished_goods_unit_id", "ALTER TABLE customer_return_lines ADD COLUMN finished_goods_unit_id INTEGER REFERENCES finished_goods_units(id)"),
    ("production_route_steps", "product_operation_id", "ALTER TABLE production_route_steps ADD COLUMN product_operation_id INTEGER REFERENCES product_operations(id)"),
    ("production_route_steps", "service_stage_id", "ALTER TABLE production_route_steps ADD COLUMN service_stage_id INTEGER REFERENCES service_stages(id)"),
    ("finished_goods_units", "initial_quantity", "ALTER TABLE finished_goods_units ADD COLUMN initial_quantity FLOAT DEFAULT 0 NOT NULL"),
)

DEFAULT_SERVICE_STAGES = (
    ("tinturaria", "Tinturaria", 10),
    ("corte", "Corte", 20),
    ("confeccao", "Confeção", 30),
    ("bordado", "Bordado", 35),
    ("estamparia", "Estamparia", 36),
    ("lavandaria", "Lavandaria", 37),
    ("revista", "Revista", 40),
    ("acabamento", "Acabamento", 45),
    ("embalagem", "Embalagem", 50),
    ("expedicao", "Expedição", 60),
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


def _seed_default_service_stages(connection) -> None:
    """Semeia etapas de produção por omissão, uma vez por empresa.

    Lista aberta e editável (não um enum fixo) — isto só dá um ponto de
    partida sensato; a empresa pode acrescentar/renomear/desativar depois.
    """
    inspector = inspect(connection)
    if "service_stages" not in inspector.get_table_names() or "companies" not in inspector.get_table_names():
        return
    company_ids = [row[0] for row in connection.execute(text("SELECT id FROM companies"))]
    seeded = {row[0] for row in connection.execute(text("SELECT DISTINCT company_id FROM service_stages"))}
    for company_id in company_ids:
        if company_id in seeded:
            continue
        for code, name, sequence in DEFAULT_SERVICE_STAGES:
            connection.execute(
                text(
                    "INSERT INTO service_stages (company_id, code, name, sequence, active) "
                    "VALUES (:company_id, :code, :name, :sequence, :active)"
                ),
                {"company_id": company_id, "code": code, "name": name, "sequence": sequence, "active": True},
            )


def _migrate_shipment_line_constraint(connection) -> None:
    """Permite várias variantes da mesma OF dentro do mesmo envio."""
    if connection.dialect.name != "postgresql":
        return
    inspector = inspect(connection)
    if "shipment_lines" not in inspector.get_table_names():
        return
    constraints = inspector.get_unique_constraints("shipment_lines")
    old = next((row for row in constraints if row.get("column_names") == ["shipment_id", "production_order_id"]), None)
    if old and old.get("name"):
        safe_name = old["name"].replace('"', '""')
        connection.execute(text(f'ALTER TABLE shipment_lines DROP CONSTRAINT "{safe_name}"'))
    refreshed = inspect(connection).get_unique_constraints("shipment_lines")
    if not any(row.get("column_names") == ["shipment_id", "production_order_id", "variant_id"] for row in refreshed):
        connection.execute(text(
            "ALTER TABLE shipment_lines ADD CONSTRAINT uq_shipment_line_variant "
            "UNIQUE (shipment_id, production_order_id, variant_id)"
        ))


def _backfill_finished_goods_initial_quantity(connection) -> None:
    """Preserva a quantidade embalada original nas unidades logísticas antigas."""
    tables = inspect(connection).get_table_names()
    if "finished_goods_units" not in tables or "shipment_allocations" not in tables:
        return
    connection.execute(text(
        "UPDATE finished_goods_units AS fg "
        "SET initial_quantity = fg.quantity + COALESCE(("
        "SELECT SUM(sa.quantity) FROM shipment_allocations AS sa "
        "WHERE sa.finished_goods_unit_id = fg.id), 0) "
        "WHERE fg.initial_quantity IS NULL OR fg.initial_quantity <= 0"
    ))


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
        _backfill_finished_goods_initial_quantity(connection)
        _migrate_shipment_line_constraint(connection)
        _migrate_subcontract_chain_to_route(connection)
        _seed_default_service_stages(connection)
