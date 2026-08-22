"""Sincronização de mestres Primavera: clientes, fornecedores, artigos, armazéns, cond. pagamento."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Bank, Customer, Material, PaymentTerm, Supplier, Warehouse
from .primavera import PrimaveraError, _api, _config, _password, _rows, _save, _token, enqueue


def pick(row: dict, *keys, default=""):
    if not isinstance(row, dict):
        return default
    lower = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
        value = lower.get(str(key).lower())
        if value not in (None, ""):
            return value
    return default


def _fetch(company, path: str) -> list[dict]:
    cfg = _config(company)
    if not (cfg.get("base_url") and _password(company)):
        raise PrimaveraError("Configure a Web API Primavera para sincronizar as tabelas.")
    token = _token(cfg, _password(company))
    _, body = _api(cfg, token, "GET", path)
    return [row for row in _rows(body) if isinstance(row, dict)]


def customer_payload(row) -> dict:
    return {
        "CustomerID": row.code,
        "Cliente": row.code,
        "Name": row.name,
        "Nome": row.name,
        "FederalTaxID": row.tax_id or "",
        "NumContrib": row.tax_id or "",
        "Address": row.address or "",
        "Morada": row.address or "",
        "ZipCode": row.postal_code or "",
        "CodPostal": row.postal_code or "",
        "City": row.city or "",
        "Localidade": row.city or "",
        "CountryID": row.country or "PT",
        "Pais": row.country or "PT",
        "Phone": row.phone or "",
        "Telefone": row.phone or "",
        "Email": row.email or "",
        "PaymentTermID": row.payment_term_code or "",
        "CondPag": row.payment_term_code or row.payment_terms or "",
        "CurrencyID": row.currency or "EUR",
        "Moeda": row.currency or "EUR",
        "Observacoes": row.notes or "",
    }


def supplier_payload(row) -> dict:
    return {
        "SupplierID": row.code,
        "Fornecedor": row.code,
        "Name": row.name,
        "Nome": row.name,
        "FederalTaxID": row.tax_id or "",
        "NumContrib": row.tax_id or "",
        "Address": row.address or "",
        "Morada": row.address or "",
        "ZipCode": row.postal_code or "",
        "CodPostal": row.postal_code or "",
        "City": row.city or "",
        "Localidade": row.city or "",
        "CountryID": row.country or "PT",
        "Phone": row.phone or "",
        "Email": row.email or "",
        "PaymentTermID": row.payment_term_code or "",
        "CondPag": row.payment_term_code or "",
        "CurrencyID": row.currency or "EUR",
        "IBAN": row.iban or "",
    }


def item_payload(row) -> dict:
    return {
        "ItemID": row.code,
        "Artigo": row.code,
        "Description": row.name,
        "Descricao": row.name,
        "UnitOfMeasureID": row.unit or "UN",
        "Unidade": row.unit or "UN",
        "Barcode": row.barcode or "",
        "CodBarras": row.barcode or "",
        "FamilyID": row.family or "",
        "Familia": row.family or "",
        "SubFamilyID": row.subfamily or "",
        "VATRateID": row.vat_code or "23",
        "Iva": row.vat_code or "23",
        "WarehouseID": row.warehouse or "",
        "Armazem": row.warehouse or "",
        "ItemType": row.item_type or "M",
        "TipoArtigo": row.item_type or "M",
        "AverageCost": row.unit_cost or 0,
        "PCMedio": row.unit_cost or 0,
    }


def bank_payload(row) -> dict:
    return {
        "BankID": row.code,
        "Banco": row.code,
        "Description": row.name,
        "Descricao": row.name,
        "Name": row.name,
        "Nome": row.name,
        "SWIFT": row.swift or "",
        "BIC": row.swift or "",
        "CountryID": row.country or "PT",
        "Pais": row.country or "PT",
        "IBANPrefix": row.iban_prefix or "",
    }


def queue_master_record(company, resource: str, row) -> dict | None:
    cfg = _config(company)
    if not (cfg.get("enabled") and cfg.get("base_url")):
        return None
    mapping = {
        "customers": ("customer", customer_payload),
        "suppliers": ("supplier", supplier_payload),
        "materials": ("item", item_payload),
        "banks": ("bank", bank_payload),
    }
    pair = mapping.get(resource)
    if not pair:
        return None
    kind, builder = pair
    payload = builder(row)
    existing = bool(getattr(row, "primavera_id", None))
    payload["_create"] = not existing
    payload["_key"] = getattr(row, "primavera_id", None) or getattr(row, "code", None)
    return enqueue(company, kind, payload, send_now=True)


def _upsert(db: Session, model, company_id: int, code: str, values: dict):
    if not code:
        return "skip"
    row = db.query(model).filter_by(company_id=company_id, code=code).first()
    created = row is None
    if created:
        row = model(company_id=company_id, code=code)
        db.add(row)
    for key, value in values.items():
        if hasattr(row, key) and value not in (None, ""):
            setattr(row, key, value)
    if hasattr(row, "sync_status"):
        row.sync_status = "synced"
    db.flush()
    return "created" if created else "updated"


def pull_customers(db: Session, company) -> dict:
    cfg = _config(company)
    created = updated = 0
    for raw in _fetch(company, cfg.get("customers_path") or "Base/Customers"):
        code = str(pick(raw, "CustomerID", "Cliente", "CustomerKey", "Key", "Codigo") or "").strip()
        action = _upsert(db, Customer, company.id, code, {
            "name": pick(raw, "Name", "Nome", "CustomerName") or code,
            "tax_id": str(pick(raw, "FederalTaxID", "NumContrib", "NIF", "TaxPayerID") or ""),
            "email": pick(raw, "Email"),
            "phone": str(pick(raw, "Phone", "Telefone", "MobilePhone") or ""),
            "address": pick(raw, "Address", "Morada", "MoradaFac"),
            "postal_code": str(pick(raw, "ZipCode", "CodPostal", "PostalCode") or ""),
            "city": pick(raw, "City", "Localidade", "Distrito"),
            "country": pick(raw, "CountryID", "Pais") or "PT",
            "payment_term_code": str(pick(raw, "PaymentTermID", "CondPag") or ""),
            "payment_terms": str(pick(raw, "PaymentTermID", "CondPag", "CondicoesPag") or ""),
            "currency": pick(raw, "CurrencyID", "Moeda") or "EUR",
            "price_list": str(pick(raw, "PriceListID", "TabelaPrecos") or ""),
            "salesperson": str(pick(raw, "SalesmanID", "Vendedor") or ""),
            "notes": pick(raw, "Remarks", "Observacoes"),
            "primavera_id": code,
            "active": True,
        })
        created += action == "created"
        updated += action == "updated"
    return {"resource": "customers", "created": created, "updated": updated}


def pull_suppliers(db: Session, company) -> dict:
    cfg = _config(company)
    created = updated = 0
    for raw in _fetch(company, cfg.get("suppliers_path") or "Base/Suppliers"):
        code = str(pick(raw, "SupplierID", "Fornecedor", "SupplierKey", "Key", "Codigo") or "").strip()
        action = _upsert(db, Supplier, company.id, code, {
            "name": pick(raw, "Name", "Nome") or code,
            "tax_id": str(pick(raw, "FederalTaxID", "NumContrib", "NIF") or ""),
            "email": pick(raw, "Email"),
            "phone": str(pick(raw, "Phone", "Telefone") or ""),
            "address": pick(raw, "Address", "Morada"),
            "postal_code": str(pick(raw, "ZipCode", "CodPostal") or ""),
            "city": pick(raw, "City", "Localidade"),
            "country": pick(raw, "CountryID", "Pais") or "PT",
            "payment_term_code": str(pick(raw, "PaymentTermID", "CondPag") or ""),
            "currency": pick(raw, "CurrencyID", "Moeda") or "EUR",
            "iban": str(pick(raw, "IBAN", "Nib") or ""),
            "contact_name": pick(raw, "Contacto", "ContactName"),
            "primavera_id": code,
            "active": True,
        })
        created += action == "created"
        updated += action == "updated"
    return {"resource": "suppliers", "created": created, "updated": updated}


def pull_items(db: Session, company) -> dict:
    cfg = _config(company)
    created = updated = 0
    for raw in _fetch(company, cfg.get("items_path") or "Base/Items"):
        code = str(pick(raw, "ItemID", "Artigo", "ItemKey", "Key", "Codigo") or "").strip()
        cost = pick(raw, "AverageCost", "PCMedio", "LastCost", "PCUltimo", "UnitCost") or 0
        try:
            cost = float(cost or 0)
        except (TypeError, ValueError):
            cost = 0
        action = _upsert(db, Material, company.id, code, {
            "name": pick(raw, "Description", "Descricao", "Name") or code,
            "unit": str(pick(raw, "UnitOfMeasureID", "Unidade", "Unit") or "un"),
            "barcode": str(pick(raw, "Barcode", "CodBarras", "EAN") or ""),
            "family": str(pick(raw, "FamilyID", "Familia") or ""),
            "subfamily": str(pick(raw, "SubFamilyID", "SubFamilia") or ""),
            "brand": str(pick(raw, "BrandID", "Marca") or ""),
            "vat_code": str(pick(raw, "VATRateID", "Iva", "TaxRate") or "23"),
            "warehouse": str(pick(raw, "WarehouseID", "Armazem") or ""),
            "item_type": str(pick(raw, "ItemType", "TipoArtigo") or "M"),
            "unit_cost": cost,
            "last_cost": cost,
            "primavera_id": code,
            "active": True,
        })
        created += action == "created"
        updated += action == "updated"
    return {"resource": "items", "created": created, "updated": updated}


def pull_warehouses(db: Session, company) -> dict:
    cfg = _config(company)
    created = updated = 0
    path = cfg.get("warehouses_path") or "Base/Warehouses"
    try:
        rows = _fetch(company, path)
    except PrimaveraError:
        return {"resource": "warehouses", "created": 0, "updated": 0, "skipped": True}
    for raw in rows:
        code = str(pick(raw, "WarehouseID", "Armazem", "Key", "Codigo") or "").strip()
        action = _upsert(db, Warehouse, company.id, code, {
            "name": pick(raw, "Description", "Descricao", "Name", "Nome") or code,
            "location": pick(raw, "Location", "Localizacao", "Morada"),
            "primavera_id": code,
            "active": True,
        })
        created += action == "created"
        updated += action == "updated"
    return {"resource": "warehouses", "created": created, "updated": updated}


def pull_payment_terms(db: Session, company) -> dict:
    cfg = _config(company)
    created = updated = 0
    path = cfg.get("payment_terms_path") or "Base/PaymentTerms"
    try:
        rows = _fetch(company, path)
    except PrimaveraError:
        return {"resource": "payment_terms", "created": 0, "updated": 0, "skipped": True}
    for raw in rows:
        code = str(pick(raw, "PaymentTermID", "CondPag", "Key", "Codigo") or "").strip()
        days = pick(raw, "Days", "Dias", "DueDays") or 0
        try:
            days = int(days or 0)
        except (TypeError, ValueError):
            days = 0
        action = _upsert(db, PaymentTerm, company.id, code, {
            "name": pick(raw, "Description", "Descricao", "Name") or code,
            "days": days,
            "primavera_id": code,
            "active": True,
        })
        created += action == "created"
        updated += action == "updated"
    return {"resource": "payment_terms", "created": created, "updated": updated}


def pull_banks(db: Session, company) -> dict:
    cfg = _config(company)
    created = updated = 0
    path = cfg.get("banks_path") or "Base/Banks"
    try:
        rows = _fetch(company, path)
    except PrimaveraError:
        return {"resource": "banks", "created": 0, "updated": 0, "skipped": True}
    for raw in rows:
        code = str(pick(raw, "BankID", "Banco", "Key", "Codigo") or "").strip()
        action = _upsert(db, Bank, company.id, code, {
            "name": pick(raw, "Description", "Descricao", "Name", "Nome") or code,
            "swift": str(pick(raw, "SWIFT", "BIC", "Swift") or ""),
            "country": pick(raw, "CountryID", "Pais") or "PT",
            "iban_prefix": str(pick(raw, "IBANPrefix", "PrefixoIBAN") or ""),
            "primavera_id": code,
            "active": True,
        })
        created += action == "created"
        updated += action == "updated"
    return {"resource": "banks", "created": created, "updated": updated}


def pull_masters(db: Session, company, resources: list[str] | None = None) -> dict:
    wanted = set(resources or ["customers", "suppliers", "items", "warehouses", "payment_terms", "banks"])
    results = []
    if "customers" in wanted:
        results.append(pull_customers(db, company))
    if "suppliers" in wanted:
        results.append(pull_suppliers(db, company))
    if "items" in wanted or "materials" in wanted:
        results.append(pull_items(db, company))
    if "warehouses" in wanted:
        results.append(pull_warehouses(db, company))
    if "payment_terms" in wanted:
        results.append(pull_payment_terms(db, company))
    if "banks" in wanted:
        results.append(pull_banks(db, company))
    cfg = _config(company)
    cfg["last_master_sync"] = {"at": datetime.now(timezone.utc).isoformat(), "results": results}
    _save(company, cfg)
    return {"ok": True, "results": results}
