"""Adaptador Primavera v10 Web API.

As credenciais ficam cifradas em company.settings. Sem licença/URL o conector
grava a fila (outbox) e não bloqueia a fábrica. Com URL e token, o mesmo código
testa a ligação e envia documentos.
"""

from __future__ import annotations

import json
import socket
import ssl
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from sqlalchemy.orm.attributes import flag_modified

from .company_profile import decrypt_secret, encrypt_secret


PUBLIC_KEYS = (
    "enabled", "base_url", "token_url", "erp_company", "instance", "line",
    "username", "verify_ssl", "timeout_seconds",
    "sales_doc_type", "sales_series", "delivery_doc_type", "delivery_series",
    "warehouse", "currency", "master",
    "customers_path", "suppliers_path", "items_path", "stock_path",
    "deliveries_path", "invoices_path",
    "requisitions_path", "purchase_deliveries_path", "goods_receipts_path",
    "purchase_invoices_path", "purchase_credits_path", "purchase_debits_path",
    "sales_credits_path", "sales_debits_path", "purchase_series",
    "warehouses_path", "payment_terms_path", "families_path", "banks_path",
)

DEFAULTS = {
    "enabled": False,
    "base_url": "",
    "token_url": "",
    "erp_company": "",
    "instance": "DEFAULT",
    "line": "professional",
    "username": "",
    "verify_ssl": False,
    "timeout_seconds": 20,
    "sales_doc_type": "FA",
    "sales_series": "A",
    "delivery_doc_type": "GT",
    "delivery_series": "A",
    "warehouse": "",
    "currency": "EUR",
    "master": "primavera",
    "customers_path": "Base/Customers",
    "suppliers_path": "Base/Suppliers",
    "items_path": "Base/Items",
    "stock_path": "Inventory/ItemWarehouses",
    "deliveries_path": "Sales/Deliveries",
    "invoices_path": "Sales/Invoices",
    "requisitions_path": "Internal/Requisitions",
    "purchase_deliveries_path": "Purchases/Deliveries",
    "goods_receipts_path": "Purchases/GoodsReceipts",
    "purchase_invoices_path": "Purchases/Invoices",
    "purchase_credits_path": "Purchases/CreditNotes",
    "purchase_debits_path": "Purchases/DebitNotes",
    "sales_credits_path": "Sales/CreditNotes",
    "sales_debits_path": "Sales/DebitNotes",
    "purchase_series": "A",
    "warehouses_path": "Base/Warehouses",
    "payment_terms_path": "Base/PaymentTerms",
    "families_path": "Base/Families",
    "banks_path": "Base/Banks",
}

CAPABILITIES = (
    {"id": "customers", "label": "Clientes", "path_key": "customers_path"},
    {"id": "suppliers", "label": "Fornecedores", "path_key": "suppliers_path"},
    {"id": "items", "label": "Artigos", "path_key": "items_path"},
    {"id": "banks", "label": "Bancos", "path_key": "banks_path"},
    {"id": "warehouses", "label": "Armazéns", "path_key": "warehouses_path"},
    {"id": "payment_terms", "label": "Condições de pagamento", "path_key": "payment_terms_path"},
    {"id": "stock", "label": "Stock / armazéns", "path_key": "stock_path"},
    {"id": "requisition", "label": "Requisições", "path_key": "requisitions_path"},
    {"id": "supplier_delivery", "label": "Guias a fornecedores", "path_key": "purchase_deliveries_path"},
    {"id": "stock_receipt", "label": "Entradas de stock", "path_key": "goods_receipts_path"},
    {"id": "purchase_invoice", "label": "Faturas de compra", "path_key": "purchase_invoices_path"},
    {"id": "purchase_credit", "label": "NC / ND de compra", "path_key": "purchase_credits_path"},
    {"id": "delivery", "label": "Guias a clientes", "path_key": "deliveries_path"},
    {"id": "invoice", "label": "Faturas de venda", "path_key": "invoices_path"},
    {"id": "sales_credit", "label": "NC / ND a clientes", "path_key": "sales_credits_path"},
)


class PrimaveraError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _config(company) -> dict:
    stored = dict((company.settings or {}).get("primavera") or {})
    data = {**DEFAULTS, **stored}
    data["outbox"] = list(stored.get("outbox") or [])
    data["last_test"] = stored.get("last_test")
    return data


def _secrets(company) -> dict:
    return dict((company.settings or {}).get("secrets") or {})


def _password(company) -> str:
    return decrypt_secret(_secrets(company).get("primavera_password")) or ""


def _save(company, cfg: dict, secrets: dict | None = None) -> None:
    settings = dict(company.settings or {})
    settings["primavera"] = cfg
    if secrets is not None:
        settings["secrets"] = secrets
    company.settings = settings
    if getattr(company, "id", None):
        flag_modified(company, "settings")


def public_status(company) -> dict:
    cfg = _config(company)
    password_set = bool(_secrets(company).get("primavera_password"))
    ready = bool(str(cfg.get("base_url") or "").strip() and str(cfg.get("erp_company") or "").strip() and str(cfg.get("username") or "").strip() and password_set)
    last = cfg.get("last_test") or {}
    connected = bool(ready and last.get("ok") and cfg.get("enabled"))
    pending = [item for item in cfg.get("outbox") or [] if item.get("status") in {"pending", "failed", "queued", "alert"}]
    alerts = [item for item in cfg.get("outbox") or [] if item.get("status") == "alert" or int(item.get("attempts") or 0) >= 3]
    if not ready:
        message = "Preencha o URL da Web API, a empresa Primavera, o utilizador técnico e a palavra-passe. A licença pode chegar depois: a fila já fica gravada."
    elif not cfg.get("enabled"):
        message = "Ligação configurada, mas ainda desligada. Ative quando a licença Web API estiver disponível."
    elif last.get("ok"):
        message = last.get("message") or "Último teste à Web API teve sucesso."
    elif last:
        message = last.get("message") or "O último teste falhou. Confirme URL, empresa, linha e licença."
    else:
        message = "Credenciais gravadas. Clique em Testar ligação quando o parceiro Primavera ativar a Web API."
    return {
        "enabled": bool(cfg.get("enabled")),
        "mode": "web-api-v10",
        "company": cfg.get("erp_company") or company.code,
        "connected": connected,
        "configured": ready,
        "password_set": password_set,
        "pending": len(pending),
        "alerts": len(alerts),
        "last_test": last or None,
        "config": {key: cfg.get(key) for key in PUBLIC_KEYS},
        "capabilities": [
            {**item, "path": cfg.get(item["path_key"]), "ready": ready}
            for item in CAPABILITIES
        ],
        "outbox": (cfg.get("outbox") or [])[-20:][::-1],
        "message": message,
    }


def apply_config(company, payload: dict) -> dict:
    cfg = _config(company)
    secrets = _secrets(company)
    for key in PUBLIC_KEYS:
        if key not in payload:
            continue
        value = payload[key]
        if key in {"enabled", "verify_ssl"}:
            cfg[key] = bool(value)
        elif key == "timeout_seconds":
            cfg[key] = max(5, min(120, int(value or 20)))
        else:
            cfg[key] = "" if value in (None, "") else str(value).strip()
    password = payload.get("password")
    if password:
        sealed = encrypt_secret(str(password))
        if sealed:
            secrets["primavera_password"] = sealed
    _save(company, cfg, secrets)
    return public_status(company)


def _ssl_context(verify: bool):
    if verify:
        return ssl.create_default_context()
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _request(cfg: dict, method: str, url: str, *, data=None, headers=None, form=False):
    timeout = int(cfg.get("timeout_seconds") or 20)
    payload = None
    req_headers = {"Accept": "application/json", "User-Agent": "TextileFlow/Primavera"}
    if headers:
        req_headers.update(headers)
    if data is not None:
        if form:
            payload = urllib.parse.urlencode(data).encode()
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            payload = json.dumps(data).encode()
            req_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=payload, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context(bool(cfg.get("verify_ssl")))) as response:
            raw = response.read().decode("utf-8", errors="replace")
            body = json.loads(raw) if raw.strip() else {}
            return response.status, body
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            body = {"error": raw[:400]}
        raise PrimaveraError(_http_message(error.code, body, raw)) from error
    except urllib.error.URLError as error:
        raise PrimaveraError(f"Não foi possível contactar o Primavera em {url}. {error.reason}") from error
    except TimeoutError as error:
        raise PrimaveraError("O Primavera não respondeu a tempo. Confirme o URL e a rede.") from error
    except socket.timeout as error:
        raise PrimaveraError("O Primavera não respondeu a tempo. Confirme o URL e a rede.") from error


def _http_message(status: int, body: dict, raw: str) -> str:
    detail = body.get("error_description") or body.get("error") or body.get("message") or body.get("ExceptionMessage")
    if isinstance(detail, dict):
        detail = detail.get("message") or str(detail)
    if status in {401, 403}:
        return "O Primavera recusou as credenciais ou a licença da Web API. Confirme utilizador, palavra-passe, empresa e se o módulo API está activo."
    if status == 404:
        return "URL ou recurso Web API não encontrado. Confirme o endereço (normalmente porta 2018) e os caminhos Base/Sales."
    return str(detail or raw[:240] or f"Erro HTTP {status} na Web API Primavera")


def _join(base: str, *parts: str) -> str:
    root = (base or "").rstrip("/")
    extra = "/".join(str(part).strip("/") for part in parts if part)
    return f"{root}/{extra}" if extra else root


def _token(cfg: dict, password: str) -> str:
    base = (cfg.get("base_url") or "").rstrip("/")
    if not base:
        raise PrimaveraError("Indique o URL da Web API Primavera")
    if not password:
        raise PrimaveraError("Indique a palavra-passe do utilizador técnico")
    token_url = (cfg.get("token_url") or "").strip() or f"{base}/token"
    _, body = _request(cfg, "POST", token_url, data={
        "grant_type": "password",
        "username": cfg.get("username") or "",
        "password": password,
        "company": cfg.get("erp_company") or "",
        "instance": cfg.get("instance") or "DEFAULT",
        "line": cfg.get("line") or "professional",
    }, form=True)
    token = body.get("access_token")
    if not token:
        raise PrimaveraError("A Web API não devolveu access_token. Confirme a linha (professional/executive) e a empresa.")
    return token


def _api(cfg: dict, token: str, method: str, path: str, data=None):
    url = _join(cfg.get("base_url") or "", cfg.get("erp_company") or "", path)
    return _request(cfg, method, url, data=data, headers={"Authorization": f"Bearer {token}"})


def test_connection(company) -> dict:
    cfg = _config(company)
    try:
        token = _token(cfg, _password(company))
        path = cfg.get("customers_path") or "Base/Customers"
        ping = path if "?" in path else f"{path}?$top=1"
        status_code, body = _api(cfg, token, "GET", ping)
        count = _count(body)
        cfg["last_test"] = {
            "ok": True, "at": _now(), "http": status_code,
            "message": f"Web API autenticada. Recurso {path} respondeu ({count} registo(s) visíveis).",
        }
        _save(company, cfg)
        return {**public_status(company), "ok": True, "message": cfg["last_test"]["message"]}
    except PrimaveraError as error:
        cfg["last_test"] = {"ok": False, "at": _now(), "message": str(error)}
        _save(company, cfg)
        return {**public_status(company), "ok": False, "message": str(error)}


def _count(body) -> int:
    if isinstance(body, list):
        return len(body)
    if isinstance(body, dict):
        for key in ("value", "Data", "data", "Results"):
            if isinstance(body.get(key), list):
                return len(body[key])
    return 1 if body else 0


def enqueue(company, kind: str, payload: dict, *, send_now: bool = True) -> dict:
    cfg = _config(company)
    item = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "status": "pending",
        "payload": payload,
        "attempts": 0,
        "created_at": _now(),
        "error": None,
        "remote_id": None,
    }
    if send_now and cfg.get("enabled") and _password(company) and cfg.get("base_url"):
        try:
            remote = _send(company, cfg, kind, payload)
            item["status"] = "sent"
            item["remote_id"] = remote
            item["sent_at"] = _now()
        except PrimaveraError as error:
            item["status"] = "failed"
            item["error"] = str(error)
    elif not (cfg.get("base_url") and _password(company)):
        item["status"] = "queued"
        item["error"] = "À espera da Web API / licença. O documento fica na fila."
    cfg["outbox"] = (cfg.get("outbox") or [])[-80:] + [item]
    _save(company, cfg)
    return item


def flush_outbox(company, *, retry_alerts: bool = False) -> dict:
    cfg = _config(company)
    sent = failed = alerts = 0
    updated = []
    for item in cfg.get("outbox") or []:
        status = item.get("status")
        attempts = int(item.get("attempts") or 0)
        if status not in {"pending", "failed", "queued", "alert"}:
            updated.append(item)
            continue
        if status == "alert" and attempts >= 3 and not retry_alerts:
            alerts += 1
            updated.append(item)
            continue
        try:
            remote = _send(company, cfg, item["kind"], item.get("payload") or {})
            item["status"] = "sent"
            item["remote_id"] = remote
            item["sent_at"] = _now()
            item["error"] = None
            item["attempts"] = 0
            sent += 1
        except PrimaveraError as error:
            attempts += 1
            item["attempts"] = attempts
            item["failed_at"] = _now()
            item["error"] = str(error)
            if attempts >= 3:
                item["status"] = "alert"
                item["error"] = f"{error} (falhou {attempts} vezes)"
                alerts += 1
            else:
                item["status"] = "failed"
                failed += 1
        updated.append(item)
    cfg["outbox"] = updated
    cfg["last_flush"] = {"at": _now(), "sent": sent, "failed": failed, "alerts": alerts}
    _save(company, cfg)
    return {"sent": sent, "failed": failed, "alerts": alerts, **public_status(company)}


def _rows(body) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("value", "Data", "data", "Results"):
            if isinstance(body.get(key), list):
                return body[key]
    return []


def fetch_stock(company) -> dict:
    cfg = _config(company)
    if not (cfg.get("base_url") and _password(company)):
        raise PrimaveraError("Configure o URL e a palavra-passe da Web API para puxar o stock.")
    token = _token(cfg, _password(company))
    path = cfg.get("stock_path") or "Inventory/ItemWarehouses"
    ping = path if "?" in path else path
    _, body = _api(cfg, token, "GET", ping)
    items = []
    for row in _rows(body):
        if not isinstance(row, dict):
            continue
        item = row.get("Artigo") or row.get("Item") or row.get("ItemKey") or row.get("ArtigoId") or row.get("Key")
        warehouse = row.get("Armazem") or row.get("Warehouse") or row.get("WarehouseKey") or row.get("ArmazemId")
        qty = row.get("StkActual") or row.get("StockActual") or row.get("Quantity") or row.get("Stock") or 0
        reserved = row.get("StkReservado") or row.get("Reserved") or row.get("StockReservado") or 0
        try:
            qty_n = float(qty or 0)
            reserved_n = float(reserved or 0)
        except (TypeError, ValueError):
            qty_n, reserved_n = 0.0, 0.0
        items.append({
            "item": str(item or ""),
            "warehouse": str(warehouse or ""),
            "quantity": qty_n,
            "reserved": reserved_n,
            "available": qty_n - reserved_n,
        })
    return {"ok": True, "count": len(items), "path": path, "items": items[:800]}


def _send(company, cfg: dict, kind: str, payload: dict):
    token = _token(cfg, _password(company))
    paths = {
        "customer": cfg.get("customers_path"),
        "supplier": cfg.get("suppliers_path"),
        "item": cfg.get("items_path"),
        "bank": cfg.get("banks_path"),
        "delivery": cfg.get("deliveries_path"),
        "invoice": cfg.get("invoices_path"),
        "stock": cfg.get("stock_path"),
        "requisition": cfg.get("requisitions_path"),
        "supplier_delivery": cfg.get("purchase_deliveries_path"),
        "stock_receipt": cfg.get("goods_receipts_path"),
        "purchase_invoice": cfg.get("purchase_invoices_path"),
        "purchase_credit": cfg.get("purchase_credits_path"),
        "purchase_debit": cfg.get("purchase_debits_path"),
        "sales_credit": cfg.get("sales_credits_path"),
        "sales_debit": cfg.get("sales_debits_path"),
    }
    path = paths.get(kind)
    if not path:
        raise PrimaveraError(f"Tipo de documento não mapeado: {kind}")
    data = dict(payload or {})
    creating = bool(data.pop("_create", True))
    key = data.pop("_key", None)
    method = "GET" if kind == "stock" else ("POST" if creating or kind not in {"customer", "supplier", "item", "bank"} else "PUT")
    if method == "PUT" and key:
        path = f"{path.rstrip('/')}/{urllib.parse.quote(str(key), safe='')}"
    status, body = _api(cfg, token, method, path, None if method == "GET" else data)
    if isinstance(body, dict):
        return str(body.get("id") or body.get("Id") or body.get("key") or body.get("NumDoc") or status)
    return str(status)


def queue_delivery(company, *, order, shipment, customer, lines) -> dict:
    cfg = _config(company)
    payload = {
        "DocumentType": cfg.get("delivery_doc_type") or "GT",
        "Serie": cfg.get("delivery_series") or "A",
        "Entity": (customer.code if customer else None) or "",
        "EntityType": "C",
        "Warehouse": cfg.get("warehouse") or "",
        "Currency": cfg.get("currency") or company.currency or "EUR",
        "YourRef": getattr(order, "order_no", None),
        "Remarks": getattr(shipment, "shipment_no", None),
        "Carrier": getattr(shipment, "carrier", None),
        "Destination": getattr(shipment, "destination", None),
        "Quantity": getattr(shipment, "quantity", None),
        "Lines": [
            {
                "Item": getattr(line, "description", None) or str(getattr(line, "style_id", "")),
                "Quantity": getattr(line, "quantity", 0),
                "UnitPrice": getattr(line, "unit_price", 0),
            }
            for line in (lines or [])
        ],
    }
    return enqueue(company, "delivery", payload)


def queue_invoice(company, *, customer_code: str, reference: str, lines: list[dict]) -> dict:
    cfg = _config(company)
    payload = {
        "DocumentType": cfg.get("sales_doc_type") or "FA",
        "Serie": cfg.get("sales_series") or "A",
        "Entity": customer_code,
        "EntityType": "C",
        "Currency": cfg.get("currency") or "EUR",
        "YourRef": reference,
        "Lines": lines,
    }
    return enqueue(company, "invoice", payload)
