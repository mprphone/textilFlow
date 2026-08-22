from ..models import Company, ProductionLine
from .seeders import ensure_confection_data, ensure_demo_followup, ensure_subcontract_catalog, seed_foundation, seed_product, seed_production
from .seeders.confection import keep_two_sewing_lines
from .modules import ensure_company_modules


def seed_database(db) -> bool:
    try:
        existing = db.query(Company).count()
        if existing:
            ensure_subcontract_catalog(db)
            ensure_confection_data(db)
            ensure_demo_followup(db)
            ensure_company_modules(db)
        else:
            foundation = seed_foundation(db)
            product = seed_product(db, foundation)
            seed_production(db, foundation, product)
            ensure_subcontract_catalog(db)
            ensure_confection_data(db)
            ensure_company_modules(db)
        for company_id, in db.query(ProductionLine.company_id).distinct().all():
            keep_two_sewing_lines(db, company_id)
        db.commit()
        return not existing
    except Exception:
        db.rollback()
        raise
