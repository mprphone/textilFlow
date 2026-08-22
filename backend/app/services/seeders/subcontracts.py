from ...models import Company, SubcontractService, Supplier


DEFAULT_SERVICES = (
    ("TIN-N", "TING-REAT", "Tingimento reativo", "dyeing", "kg", 0.62, 10),
    ("TIN-N", "EST-PIG", "Estampagem pigmento", "printing", "un", 0.70, 8),
    ("TIN-N", "LAV-IND", "Lavagem industrial", "laundry", "un", 0.38, 7),
    ("CONF-S", "CONF-COMP", "Confeção completa", "sewing", "un", 3.50, 12),
    ("CONF-S", "ACAB-FIN", "Acabamento e revisão final", "finishing", "un", 0.42, 5),
)


def ensure_subcontract_catalog(db) -> int:
    """Cria apenas exemplos em falta, também em bases já inicializadas."""

    created = 0
    for company in db.query(Company).all():
        suppliers = {
            row.code: row for row in db.query(Supplier).filter_by(company_id=company.id).all()
        }
        for supplier_code, code, name, category, unit, cost, lead_time in DEFAULT_SERVICES:
            supplier = suppliers.get(supplier_code)
            if not supplier:
                continue
            exists = db.query(SubcontractService).filter_by(
                company_id=company.id, supplier_id=supplier.id, code=code
            ).first()
            if exists:
                continue
            db.add(SubcontractService(
                company_id=company.id,
                supplier_id=supplier.id,
                code=code,
                name=name,
                category=category,
                unit=unit,
                unit_cost=cost,
                lead_time_days=lead_time,
                quality_score=supplier.score or 0,
            ))
            created += 1
    return created
