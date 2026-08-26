"""Leitura de faturas (foto/PDF) via Gemini e aprendizagem de artigos."""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..models import CommercialDocument, Company, Customer, ItemAlias, Material, Supplier
from .commercial_docs import create_document, prepare_primavera, public_document, receive_stock
from .company_profile import decrypt_secret, encrypt_secret


GEMINI_MODELS = ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-latest")
PROMPT = """És o leitor de documentos fiscais portugueses do TextileFlow, um ERP têxtil.
Extrai a fatura, guia, NC, ND ou requisição desta imagem/PDF.
Devolve APENAS JSON válido, sem markdown, com esta forma:
{
  "doc_type": "purchase_invoice|purchase_credit|purchase_debit|supplier_transport|requisition|sales_invoice|sales_credit|sales_debit|sales_delivery",
  "number": "número do documento",
  "date": "YYYY-MM-DD ou vazio",
  "supplier_name": "",
  "supplier_tax_id": "NIF sem espaços",
  "customer_name": "",
  "customer_tax_id": "",
  "currency": "EUR",
  "total": 0,
  "notes": "",
  "lines": [
    {"code": "código do artigo no documento", "description": "designação", "quantity": 0, "unit": "un", "unit_cost": 0, "vat": 23}
  ]
}
Regras: doc_type purchase_* se for documento de fornecedor/compra; sales_* se for fatura nossa a cliente.
Quantidades e preços são números. Se não souberes um campo, usa string vazia ou 0.
"""


def normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def gemini_configured(company: Company) -> bool:
    secrets = dict((company.settings or {}).get("secrets") or {})
    return bool(decrypt_secret(secrets.get("gemini_api_key")))


def save_gemini_key(company: Company, api_key: str) -> None:
    settings = dict(company.settings or {})
    secrets = dict(settings.get("secrets") or {})
    sealed = encrypt_secret(api_key)
    if sealed:
        secrets["gemini_api_key"] = sealed
    settings["secrets"] = secrets
    company.settings = settings
    if getattr(company, "id", None):
        flag_modified(company, "settings")


def _api_key(company: Company) -> str:
    secrets = dict((company.settings or {}).get("secrets") or {})
    key = decrypt_secret(secrets.get("gemini_api_key")) or ""
    if not key.strip():
        raise HTTPException(409, "Indique a chave da API Gemini em ERP → Ler fatura. Sem ela o programa não lê fotos nem PDFs.")
    return key.strip()


def _call_gemini(api_key: str, mime: str, data_b64: str) -> dict:
    body = {
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {"inlineData": {"mimeType": mime, "data": data_b64}},
            ]
        }],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    payload = json.dumps(body).encode()
    last_error = None
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={urllib.parse.quote(api_key)}"
        request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = json.loads(response.read().decode("utf-8", errors="replace"))
            text = (
                raw.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text") or ""
            )
            return _parse_json(text)
        except urllib.error.HTTPError as error:
            last_error = error.read().decode("utf-8", errors="replace")[:300]
            continue
        except Exception as error:
            last_error = str(error)
            continue
    raise HTTPException(502, f"A Gemini não leu o documento. {last_error or ''}".strip())


def _parse_json(text: str) -> dict:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).replace("```", "").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as error:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise HTTPException(422, "A Gemini não devolveu um JSON válido. Tente uma foto mais nítida.") from error
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise HTTPException(422, "Leitura inválida do documento")
    return data


def parse_document(company: Company, *, mime: str, data_b64: str) -> dict:
    allowed = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
    if mime not in allowed:
        raise HTTPException(422, "Use uma fotografia JPEG/PNG ou um PDF")
    blob = re.sub(r"^data:[^;]+;base64,", "", data_b64 or "")
    if len(blob) < 80:
        raise HTTPException(422, "O ficheiro está vazio")
    if len(blob) > 12_000_000:
        raise HTTPException(413, "O ficheiro é demasiado grande. Tire uma foto mais leve ou um PDF mais pequeno.")
    return _call_gemini(_api_key(company), mime, blob)


def match_supplier(db: Session, company_id: int, parsed: dict) -> Supplier | None:
    nif = re.sub(r"[^0-9A-Za-z]", "", parsed.get("supplier_tax_id") or "").upper()
    if nif.startswith("PT"):
        nif = nif[2:]
    name = normalize(parsed.get("supplier_name"))
    suppliers = db.query(Supplier).filter_by(company_id=company_id, active=True).all()
    for supplier in suppliers:
        tax = re.sub(r"[^0-9A-Za-z]", "", supplier.tax_id or "").upper().removeprefix("PT")
        if nif and tax and nif[-9:] == tax[-9:]:
            return supplier
    for supplier in suppliers:
        if name and (name == normalize(supplier.name) or name in normalize(supplier.name) or normalize(supplier.name) in name):
            return supplier
    return None


def match_customer(db: Session, company_id: int, parsed: dict) -> Customer | None:
    nif = re.sub(r"[^0-9A-Za-z]", "", parsed.get("customer_tax_id") or "").upper().removeprefix("PT")
    name = normalize(parsed.get("customer_name"))
    customers = db.query(Customer).filter_by(company_id=company_id, active=True).all()
    for customer in customers:
        tax = re.sub(r"[^0-9A-Za-z]", "", customer.tax_id or "").upper().removeprefix("PT")
        if nif and tax and nif[-9:] == tax[-9:]:
            return customer
    for customer in customers:
        if name and (name == normalize(customer.name) or name in normalize(customer.name)):
            return customer
    return None


def match_line(db: Session, company_id: int, supplier_id: int | None, line: dict) -> dict:
    code = str(line.get("code") or "").strip()
    name = str(line.get("description") or "").strip()
    key = normalize(f"{code} {name}")
    aliases = db.query(ItemAlias).filter_by(company_id=company_id).all()
    ranked = []
    for alias in aliases:
        score = 0
        if supplier_id and alias.supplier_id == supplier_id:
            score += 2
        if code and normalize(alias.source_code) == normalize(code):
            score += 8
        if key and alias.normalized and alias.normalized == key:
            score += 6
        elif name and alias.normalized and (alias.normalized in normalize(name) or normalize(name) in alias.normalized):
            score += 3
        if score:
            ranked.append((score + alias.hits, alias))
    if ranked:
        ranked.sort(key=lambda item: item[0], reverse=True)
        alias = ranked[0][1]
        material = db.get(Material, alias.material_id)
        if material:
            return {"material_id": material.id, "code": material.code, "description": material.name, "learned": True, "confidence": min(0.99, 0.55 + alias.hits * 0.05)}
    materials = db.query(Material).filter_by(company_id=company_id, active=True).all()
    for material in materials:
        if code and normalize(material.code) == normalize(code):
            return {"material_id": material.id, "code": material.code, "description": material.name, "learned": False, "confidence": 0.85}
    for material in materials:
        if name and normalize(material.name) == normalize(name):
            return {"material_id": material.id, "code": material.code, "description": material.name, "learned": False, "confidence": 0.75}
    for material in materials:
        blob = f"{material.code} {material.name}"
        if key and (key in normalize(blob) or normalize(material.name) in key):
            return {"material_id": material.id, "code": material.code, "description": material.name, "learned": False, "confidence": 0.45}
    return {"material_id": None, "code": code, "description": name, "learned": False, "confidence": 0}


def preview_capture(db: Session, company: Company, parsed: dict) -> dict:
    supplier = match_supplier(db, company.id, parsed)
    customer = match_customer(db, company.id, parsed)
    doc_type = parsed.get("doc_type") or "purchase_invoice"
    lines = []
    for raw in parsed.get("lines") or []:
        matched = match_line(db, company.id, supplier.id if supplier else None, raw)
        lines.append({
            **matched,
            "source_code": raw.get("code") or "",
            "source_name": raw.get("description") or "",
            "quantity": float(raw.get("quantity") or 0),
            "unit": raw.get("unit") or "un",
            "unit_cost": float(raw.get("unit_cost") or 0),
            "vat": float(raw.get("vat") or 0),
        })
    return {
        "gemini_ok": True,
        "doc_type": doc_type,
        "number": parsed.get("number") or "",
        "date": parsed.get("date") or str(date.today()),
        "currency": parsed.get("currency") or "EUR",
        "total": parsed.get("total") or 0,
        "notes": parsed.get("notes") or "",
        "supplier_id": supplier.id if supplier else None,
        "supplier_name": (supplier.name if supplier else None) or parsed.get("supplier_name"),
        "supplier_tax_id": parsed.get("supplier_tax_id"),
        "customer_id": customer.id if customer else None,
        "customer_name": (customer.name if customer else None) or parsed.get("customer_name"),
        "unmatched": sum(1 for line in lines if not line.get("material_id")),
        "learned": sum(1 for line in lines if line.get("learned")),
        "lines": lines,
        "raw": parsed,
    }


def remember_alias(db: Session, company_id: int, supplier_id: int | None, source_code: str, source_name: str, material_id: int) -> ItemAlias:
    key = normalize(f"{source_code} {source_name}")
    alias = db.query(ItemAlias).filter_by(
        company_id=company_id, supplier_id=supplier_id or None,
        source_code=source_code or "", normalized=key, material_id=material_id,
    ).first()
    if alias:
        alias.hits = int(alias.hits or 0) + 1
        alias.confidence = min(1.0, float(alias.confidence or 0) + 0.05)
        return alias
    alias = ItemAlias(
        company_id=company_id, supplier_id=supplier_id, source_code=source_code or "",
        source_name=source_name or "", normalized=key, material_id=material_id, hits=1, confidence=0.7,
    )
    db.add(alias)
    db.flush()
    return alias


def list_aliases(db: Session, company_id: int) -> list[dict]:
    rows = db.query(ItemAlias).filter_by(company_id=company_id).order_by(ItemAlias.hits.desc(), ItemAlias.id.desc()).limit(400).all()
    data = []
    for alias in rows:
        material = db.get(Material, alias.material_id)
        supplier = db.get(Supplier, alias.supplier_id) if alias.supplier_id else None
        data.append({
            "id": alias.id,
            "source_code": alias.source_code,
            "source_name": alias.source_name,
            "hits": alias.hits,
            "confidence": alias.confidence,
            "material_id": alias.material_id,
            "material": f"{material.code} · {material.name}" if material else "—",
            "supplier": supplier.name if supplier else "Qualquer fornecedor",
        })
    return data


def confirm_capture(db: Session, company: Company, payload: dict) -> dict:
    doc_type = payload.get("doc_type") or "purchase_invoice"
    lines_in = payload.get("lines") or []
    mapped = []
    for line in lines_in:
        material_id = line.get("material_id")
        if not material_id:
            continue
        mapped.append({
            "material_id": material_id,
            "quantity": line.get("quantity") or 0,
            "unit_cost": line.get("unit_cost") or 0,
            "unit": line.get("unit") or "un",
            "description": line.get("description") or line.get("source_name"),
            "code": line.get("code") or line.get("source_code"),
        })
        remember_alias(
            db, company.id, payload.get("supplier_id"),
            str(line.get("source_code") or ""), str(line.get("source_name") or line.get("description") or ""),
            int(material_id),
        )
    if not mapped:
        raise HTTPException(422, "Ligue pelo menos uma linha a um artigo TextileFlow. Da próxima vez o programa lembra-se.")
    number = str(payload.get("number") or "").strip()
    if number and db.query(CommercialDocument).filter_by(company_id=company.id, doc_no=number).first():
        payload["notes"] = f"N.º original {number}. {payload.get('notes') or ''}".strip()
        number = None
    document = create_document(db, company.id, {
        "doc_type": doc_type,
        "doc_no": number or None,
        "doc_date": payload.get("date") or date.today(),
        "supplier_id": payload.get("supplier_id"),
        "customer_id": payload.get("customer_id"),
        "currency": payload.get("currency") or "EUR",
        "notes": payload.get("notes") or "Lido por fotografia / PDF (Gemini)",
        "lines": mapped,
        "extra": {"capture": payload.get("raw") or {}, "source": "gemini", "original_number": payload.get("number")},
    })
    if payload.get("prepare", True):
        prepare_primavera(db, company, document)
    follow = {"purchase_invoice": "stock_receipt", "supplier_transport": "stock_receipt"}.get(doc_type)
    extra_docs = []
    if follow:
        extra = create_document(db, company.id, {
            "doc_type": follow,
            "supplier_id": document.supplier_id,
            "customer_id": document.customer_id,
            "converted_from_id": document.id,
            "currency": document.currency,
            "notes": f"Gerado automaticamente a partir de {document.doc_no}",
            "lines": mapped,
        })
        if follow == "stock_receipt":
            receive_stock(db, company.id, extra)
        if payload.get("prepare", True):
            prepare_primavera(db, company, extra)
        extra_docs.append(public_document(db, extra))
    data = public_document(db, document)
    data["follow_on"] = extra_docs
    return data
