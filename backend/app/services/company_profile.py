import base64
import hashlib
import hmac
import os
import re

from sqlalchemy.orm.attributes import flag_modified

from ..auth import SECRET

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover - fallback se a imagem Docker ainda não tiver o pacote
    Fernet = None
    InvalidToken = Exception

PROFILE_KEYS = (
    "legal_name", "legal_form", "address", "address_extra", "postal_code", "city", "district",
    "country", "phone", "email", "website", "cae", "conservatory_no", "commercial_registry",
    "social_security_no", "share_capital", "share_capital_currency", "iban", "bic", "manager_name",
    "billing_software", "billing_api_url", "billing_company_code",
)
SECRET_KEYS = ("tax_password", "billing_api_key", "billing_password")
COMPANY_STATUSES = ("active", "inactive", "suspended")


class CompanyProfileError(ValueError):
    pass


def _key() -> bytes:
    return hashlib.sha256(f"textileflow-company-secret:{SECRET}".encode()).digest()


def _fernet():
    if Fernet is None:
        return None
    digest = hashlib.sha256(f"textileflow-fernet:{SECRET}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str | None) -> str | None:
    text = (plain or "").strip()
    if not text:
        return None
    box = _fernet()
    if box is not None:
        return "tf2:" + box.encrypt(text.encode("utf-8")).decode("ascii")
    raw = text.encode("utf-8")
    key = _key()
    nonce = os.urandom(16)
    stream = hashlib.sha256(key + nonce).digest()
    while len(stream) < len(raw):
        stream += hashlib.sha256(stream).digest()
    cipher = bytes(left ^ right for left, right in zip(raw, stream))
    mac = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    return "tf1:" + base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")


def decrypt_secret(token: str | None) -> str | None:
    if not token:
        return None
    text = str(token)
    if text.startswith("tf2:"):
        box = _fernet()
        if box is None:
            return None
        try:
            return box.decrypt(text[4:].encode("ascii")).decode("utf-8")
        except (InvalidToken, Exception):
            return None
    if not text.startswith("tf1:"):
        return None
    try:
        blob = base64.urlsafe_b64decode(text[4:].encode("ascii"))
        nonce, mac, cipher = blob[:16], blob[16:48], blob[48:]
        key = _key()
        expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            return None
        stream = hashlib.sha256(key + nonce).digest()
        while len(stream) < len(cipher):
            stream += hashlib.sha256(stream).digest()
        return bytes(left ^ right for left, right in zip(cipher, stream)).decode("utf-8")
    except Exception:
        return None


def normalize_nif(value: str | None) -> str:
    compact = re.sub(r"[^0-9A-Za-z]", "", (value or "")).upper()
    if compact.startswith("PT") and len(compact) > 2:
        compact = compact[2:]
    return compact


def validate_nif(value: str | None) -> str:
    nif = normalize_nif(value)
    if not nif:
        raise CompanyProfileError("Indique o NIF da empresa")
    if not nif.isdigit() or len(nif) != 9:
        raise CompanyProfileError("O NIF português tem 9 dígitos")
    if nif[0] not in "12356789":
        raise CompanyProfileError("O NIF não tem um prefixo válido para empresas ou empresários em Portugal")
    total = sum(int(digit) * weight for digit, weight in zip(nif[:8], range(9, 1, -1)))
    check = 11 - (total % 11)
    if check >= 10:
        check = 0
    if check != int(nif[8]):
        raise CompanyProfileError("O NIF não é válido. Confirme os dígitos antes de gravar.")
    return nif


def nif_is_locked(tax_id: str | None) -> bool:
    try:
        return bool(tax_id) and bool(validate_nif(tax_id))
    except CompanyProfileError:
        return False


def resolve_status(company) -> str:
    settings = dict(company.settings or {})
    raw = str(settings.get("life_status") or "").strip().lower()
    if company.active is False:
        if raw == "suspended":
            return "suspended"
        return "inactive"
    if raw in COMPANY_STATUSES:
        return raw
    return "active"


def _secrets(settings: dict) -> dict:
    return dict((settings or {}).get("secrets") or {})


def public_company(company) -> dict:
    from .modules import enabled_modules
    from .serialization import model_to_dict
    settings = dict(company.settings or {})
    profile = dict(settings.get("profile") or {})
    secrets = _secrets(settings)
    data = model_to_dict(company)
    data.pop("settings", None)
    data["enabled_modules"] = enabled_modules(company)
    data["profile"] = {key: profile.get(key) for key in PROFILE_KEYS}
    data["status"] = resolve_status(company)
    data["nif_locked"] = nif_is_locked(company.tax_id)
    data["tax_password_set"] = bool(secrets.get("tax_password"))
    data["billing_api_key_set"] = bool(secrets.get("billing_api_key"))
    data["billing_password_set"] = bool(secrets.get("billing_password"))
    return data


def apply_company_payload(company, payload: dict, *, creating: bool = False) -> None:
    settings = dict(company.settings or {})
    profile = dict(settings.get("profile") or {})
    secrets = _secrets(settings)

    if "tax_id" in payload or creating:
        incoming = payload.get("tax_id")
        if incoming:
            nif = validate_nif(incoming)
            if not creating and nif_is_locked(company.tax_id) and normalize_nif(company.tax_id) != nif:
                raise CompanyProfileError("O NIF já está validado e não pode ser alterado")
            company.tax_id = nif
        elif creating:
            raise CompanyProfileError("O NIF é obrigatório")

    incoming_status = payload.get("status")
    if incoming_status not in (None, ""):
        status = str(incoming_status).strip().lower()
        if status not in COMPANY_STATUSES:
            raise CompanyProfileError("Estado da empresa inválido")
        settings["life_status"] = status
        company.active = status == "active"
    elif "active" in payload and payload["active"] is not None:
        company.active = bool(payload["active"])
        if company.active:
            settings["life_status"] = "active"
        elif str(settings.get("life_status") or "") not in ("inactive", "suspended"):
            settings["life_status"] = "inactive"

    for key in ("code", "name", "currency", "timezone"):
        if key in payload and payload[key] is not None:
            setattr(company, key, payload[key])

    for key in PROFILE_KEYS:
        if key in payload:
            value = payload[key]
            profile[key] = None if value in ("", None) else value
    settings["profile"] = profile

    for key in SECRET_KEYS:
        if key not in payload:
            continue
        value = payload.get(key)
        if value in (None, ""):
            continue
        sealed = encrypt_secret(str(value))
        if sealed:
            secrets[key] = sealed
    settings["secrets"] = secrets
    company.settings = settings
    software = str(profile.get("billing_software") or "").strip().lower()
    if software in ("primavera", "moloni", "generic"):
        from .erp_flavor import set_system
        set_system(company, software)
    if getattr(company, "id", None):
        flag_modified(company, "settings")
