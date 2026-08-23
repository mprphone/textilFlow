"""Contas de email da empresa: configuração, envio (SMTP) e leitura (IMAP).

As contas ficam em ``company.settings["email_accounts"]`` e as senhas cifradas em
``company.settings["secrets"]``, seguindo o mesmo esquema das restantes credenciais.
"""

from __future__ import annotations

import email
import imaplib
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr, parsedate_to_datetime

from sqlalchemy.orm.attributes import flag_modified

from .company_profile import decrypt_secret, encrypt_secret

TIMEOUT = 20
PURPOSES = ("send", "read", "both")
SECURITIES = ("ssl", "starttls", "none")
PUBLIC_KEYS = (
    "label", "email", "from_name", "purpose", "active", "is_default", "signature",
    "smtp_host", "smtp_port", "smtp_security", "smtp_user",
    "imap_host", "imap_port", "imap_security", "imap_user", "imap_folder",
)
DEFAULTS = {
    "label": "Caixa principal",
    "email": "",
    "from_name": "",
    "purpose": "both",
    "active": True,
    "is_default": False,
    "signature": "",
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_security": "starttls",
    "smtp_user": "",
    "imap_host": "",
    "imap_port": 993,
    "imap_security": "ssl",
    "imap_user": "",
    "imap_folder": "INBOX",
}


class MailboxError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settings(company) -> dict:
    return dict(company.settings or {})


def _save(company, settings: dict) -> None:
    company.settings = settings
    if getattr(company, "id", None):
        flag_modified(company, "settings")


def _accounts(settings: dict) -> list[dict]:
    return [dict(row) for row in (settings.get("email_accounts") or []) if isinstance(row, dict)]


def _secret_key(account_id: int, kind: str) -> str:
    return f"email_{account_id}_{kind}_password"


def _password(company, account: dict, kind: str) -> str:
    secrets = dict(_settings(company).get("secrets") or {})
    token = secrets.get(_secret_key(account["id"], kind))
    if not token and kind == "imap":
        token = secrets.get(_secret_key(account["id"], "smtp"))
    return decrypt_secret(token) or ""


def _int(value, fallback: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    return number if 0 < number < 65536 else fallback


def _clean(payload: dict, base: dict) -> dict:
    row = {**DEFAULTS, **base}
    for key in PUBLIC_KEYS:
        if key not in payload:
            continue
        value = payload[key]
        if key in ("smtp_port", "imap_port"):
            row[key] = _int(value, DEFAULTS[key])
        elif key in ("active", "is_default"):
            row[key] = bool(value)
        else:
            row[key] = ("" if value is None else str(value)).strip()
    if row["purpose"] not in PURPOSES:
        row["purpose"] = "both"
    for key in ("smtp_security", "imap_security"):
        if row[key] not in SECURITIES:
            row[key] = DEFAULTS[key]
    if not row["email"] or "@" not in row["email"]:
        raise MailboxError("Indique o endereço de email da conta")
    if not row["label"]:
        row["label"] = row["email"]
    if not row["smtp_user"]:
        row["smtp_user"] = row["email"]
    if not row["imap_user"]:
        row["imap_user"] = row["email"]
    if not row["imap_folder"]:
        row["imap_folder"] = "INBOX"
    return row


def public_account(company, account: dict) -> dict:
    secrets = dict(_settings(company).get("secrets") or {})
    data = {key: account.get(key, DEFAULTS.get(key)) for key in PUBLIC_KEYS}
    data["id"] = account["id"]
    data["created_at"] = account.get("created_at")
    data["last_test"] = account.get("last_test")
    data["password_set"] = bool(secrets.get(_secret_key(account["id"], "smtp")))
    data["imap_password_set"] = bool(secrets.get(_secret_key(account["id"], "imap")))
    data["can_send"] = bool(data["smtp_host"] and data["password_set"] and data["purpose"] in ("send", "both"))
    data["can_read"] = bool(data["imap_host"] and (data["imap_password_set"] or data["password_set"]) and data["purpose"] in ("read", "both"))
    return data


def list_accounts(company) -> list[dict]:
    return [public_account(company, row) for row in _accounts(_settings(company))]


def get_account(company, account_id: int) -> dict:
    for row in _accounts(_settings(company)):
        if int(row.get("id") or 0) == int(account_id):
            return row
    raise MailboxError("Conta de email não encontrada")


def upsert_account(company, payload: dict, account_id: int | None = None) -> dict:
    settings = _settings(company)
    rows = _accounts(settings)
    secrets = dict(settings.get("secrets") or {})
    if account_id:
        index = next((pos for pos, row in enumerate(rows) if int(row.get("id") or 0) == int(account_id)), None)
        if index is None:
            raise MailboxError("Conta de email não encontrada")
        row = _clean(payload, rows[index])
        row["id"] = int(account_id)
        row["created_at"] = rows[index].get("created_at") or _now()
        row["last_test"] = rows[index].get("last_test")
        rows[index] = row
    else:
        new_id = max([int(item.get("id") or 0) for item in rows], default=0) + 1
        row = _clean(payload, {})
        row["id"] = new_id
        row["created_at"] = _now()
        rows.append(row)
    for kind, field in (("smtp", "password"), ("imap", "imap_password")):
        value = payload.get(field)
        if value in (None, ""):
            continue
        sealed = encrypt_secret(str(value))
        if sealed:
            secrets[_secret_key(row["id"], kind)] = sealed
    if row.get("is_default"):
        for item in rows:
            item["is_default"] = int(item["id"]) == int(row["id"])
    elif not any(item.get("is_default") for item in rows):
        rows[0]["is_default"] = True
    settings["email_accounts"] = rows
    settings["secrets"] = secrets
    _save(company, settings)
    return public_account(company, row)


def delete_account(company, account_id: int) -> None:
    settings = _settings(company)
    rows = _accounts(settings)
    remaining = [row for row in rows if int(row.get("id") or 0) != int(account_id)]
    if len(remaining) == len(rows):
        raise MailboxError("Conta de email não encontrada")
    secrets = dict(settings.get("secrets") or {})
    for kind in ("smtp", "imap"):
        secrets.pop(_secret_key(int(account_id), kind), None)
    if remaining and not any(row.get("is_default") for row in remaining):
        remaining[0]["is_default"] = True
    settings["email_accounts"] = remaining
    settings["secrets"] = secrets
    _save(company, settings)


def default_account(company, purpose: str = "send") -> dict | None:
    rows = [row for row in _accounts(_settings(company)) if row.get("active")]
    usable = [row for row in rows if row.get("purpose") in (purpose, "both")]
    if not usable:
        return None
    return next((row for row in usable if row.get("is_default")), usable[0])


# ----------------------------------------------------------------------------- ligações


def _smtp(company, account: dict):
    host = (account.get("smtp_host") or "").strip()
    if not host:
        raise MailboxError("Servidor SMTP não configurado nesta conta")
    port = _int(account.get("smtp_port"), 587)
    security = account.get("smtp_security") or "starttls"
    context = ssl.create_default_context()
    if security == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=TIMEOUT)
        if security == "starttls":
            server.starttls(context=context)
    password = _password(company, account, "smtp")
    if password:
        server.login(account.get("smtp_user") or account["email"], password)
    return server


def _imap(company, account: dict):
    host = (account.get("imap_host") or "").strip()
    if not host:
        raise MailboxError("Servidor IMAP não configurado nesta conta")
    port = _int(account.get("imap_port"), 993)
    security = account.get("imap_security") or "ssl"
    if security == "ssl":
        conn = imaplib.IMAP4_SSL(host, port, timeout=TIMEOUT)
    else:
        conn = imaplib.IMAP4(host, port, timeout=TIMEOUT)
        if security == "starttls":
            conn.starttls(ssl.create_default_context())
    password = _password(company, account, "imap")
    if not password:
        raise MailboxError("Senha da caixa de correio em falta")
    conn.login(account.get("imap_user") or account["email"], password)
    return conn


def _friendly(error: Exception) -> str:
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "Utilizador ou senha recusados pelo servidor de envio."
    if isinstance(error, imaplib.IMAP4.error):
        return f"O servidor de leitura recusou a ligação: {error}"
    if isinstance(error, (smtplib.SMTPException, OSError)):
        return f"Não foi possível ligar ao servidor: {error}"
    return str(error) or "Erro desconhecido na ligação."


def test_account(company, account_id: int, mode: str = "both") -> dict:
    account = get_account(company, account_id)
    checks = []
    wants_send = mode in ("both", "smtp") and account.get("purpose") in ("send", "both")
    wants_read = mode in ("both", "imap") and account.get("purpose") in ("read", "both")
    if wants_send:
        try:
            server = _smtp(company, account)
            server.quit()
            checks.append({"mode": "smtp", "ok": True, "detail": "Servidor de envio autenticado."})
        except Exception as error:  # noqa: BLE001 - queremos devolver a mensagem ao utilizador
            checks.append({"mode": "smtp", "ok": False, "detail": _friendly(error)})
    if wants_read:
        try:
            conn = _imap(company, account)
            conn.select(account.get("imap_folder") or "INBOX", readonly=True)
            conn.logout()
            checks.append({"mode": "imap", "ok": True, "detail": "Caixa de correio acessível."})
        except Exception as error:  # noqa: BLE001
            checks.append({"mode": "imap", "ok": False, "detail": _friendly(error)})
    if not checks:
        raise MailboxError("Nada para testar: reveja a finalidade e os servidores da conta.")
    result = {"at": _now(), "ok": all(item["ok"] for item in checks), "checks": checks}
    settings = _settings(company)
    rows = _accounts(settings)
    for row in rows:
        if int(row.get("id") or 0) == int(account_id):
            row["last_test"] = result
    settings["email_accounts"] = rows
    _save(company, settings)
    return result


def send_email(company, account_id: int | None, *, to, subject: str, body: str,
               cc=None, bcc=None, reply_to: str | None = None, html: str | None = None) -> dict:
    account = get_account(company, account_id) if account_id else default_account(company, "send")
    if not account:
        raise MailboxError("Não existe nenhuma conta de envio configurada.")
    recipients = [addr.strip() for addr in (to if isinstance(to, list) else str(to or "").split(",")) if addr.strip()]
    copies = [addr.strip() for addr in (cc if isinstance(cc, list) else str(cc or "").split(",")) if addr.strip()]
    blind = [addr.strip() for addr in (bcc if isinstance(bcc, list) else str(bcc or "").split(",")) if addr.strip()]
    if not recipients:
        raise MailboxError("Indique pelo menos um destinatário")
    if not (subject or "").strip():
        raise MailboxError("Indique o assunto da mensagem")
    signature = (account.get("signature") or "").strip()
    text = body or ""
    if signature:
        text = f"{text}\n\n--\n{signature}"
    message = EmailMessage()
    message["From"] = formataddr((account.get("from_name") or company.name, account["email"]))
    message["To"] = ", ".join(recipients)
    if copies:
        message["Cc"] = ", ".join(copies)
    if reply_to:
        message["Reply-To"] = reply_to
    message["Subject"] = subject
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    try:
        server = _smtp(company, account)
        server.send_message(message, to_addrs=recipients + copies + blind)
        server.quit()
    except Exception as error:  # noqa: BLE001
        raise MailboxError(_friendly(error)) from error
    return {"sent": True, "account_id": account["id"], "to": recipients, "subject": subject, "at": _now()}


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return str(value)


def _when(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except Exception:  # noqa: BLE001
        return None


def _plain_text(message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition") or ""):
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        for part in message.walk():
            if part.get_content_type() == "text/html":
                raw = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                return re.sub(r"<[^>]+>", " ", raw)
        return ""
    payload = message.get_payload(decode=True)
    if payload is None:
        return str(message.get_payload() or "")
    text = payload.decode(message.get_content_charset() or "utf-8", "replace")
    return re.sub(r"<[^>]+>", " ", text) if message.get_content_type() == "text/html" else text


def list_messages(company, account_id: int, *, folder: str | None = None, limit: int = 20, unseen_only: bool = False) -> dict:
    account = get_account(company, account_id)
    if account.get("purpose") not in ("read", "both"):
        raise MailboxError("Esta conta está configurada apenas para envio.")
    box = folder or account.get("imap_folder") or "INBOX"
    try:
        conn = _imap(company, account)
        conn.select(box, readonly=True)
        status, data = conn.uid("search", None, "UNSEEN" if unseen_only else "ALL")
        if status != "OK":
            raise MailboxError("Não foi possível listar as mensagens desta pasta.")
        uids = (data[0] or b"").split()[-max(1, min(int(limit or 20), 50)):]
        items = []
        for uid in reversed(uids):
            status, payload = conn.uid("fetch", uid, "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
            if status != "OK" or not payload or not isinstance(payload[0], tuple):
                continue
            flags = str(payload[0][0])
            header = email.message_from_bytes(payload[0][1])
            items.append({
                "uid": uid.decode(),
                "from": _decode(header.get("From")),
                "to": _decode(header.get("To")),
                "subject": _decode(header.get("Subject")) or "(sem assunto)",
                "date": _when(header.get("Date")),
                "seen": "\\Seen" in flags,
                "answered": "\\Answered" in flags,
            })
        conn.logout()
    except MailboxError:
        raise
    except Exception as error:  # noqa: BLE001
        raise MailboxError(_friendly(error)) from error
    return {"folder": box, "items": items, "at": _now()}


def read_message(company, account_id: int, uid: str, folder: str | None = None) -> dict:
    account = get_account(company, account_id)
    box = folder or account.get("imap_folder") or "INBOX"
    try:
        conn = _imap(company, account)
        conn.select(box, readonly=True)
        status, payload = conn.uid("fetch", str(uid), "(BODY.PEEK[])")
        if status != "OK" or not payload or not isinstance(payload[0], tuple):
            raise MailboxError("Mensagem não encontrada.")
        message = email.message_from_bytes(payload[0][1])
        conn.logout()
    except MailboxError:
        raise
    except Exception as error:  # noqa: BLE001
        raise MailboxError(_friendly(error)) from error
    attachments = [
        _decode(part.get_filename())
        for part in (message.walk() if message.is_multipart() else [])
        if part.get_filename()
    ]
    return {
        "uid": str(uid),
        "folder": box,
        "from": _decode(message.get("From")),
        "to": _decode(message.get("To")),
        "cc": _decode(message.get("Cc")),
        "subject": _decode(message.get("Subject")) or "(sem assunto)",
        "date": _when(message.get("Date")),
        "body": _plain_text(message).strip(),
        "attachments": attachments,
    }
