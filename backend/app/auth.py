import logging
import os
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext


WEAK_SECRETS = {
    "",
    "change-me-in-production",
    "change-me-before-production",
    "substituir-por-uma-chave-longa-aleatoria",
}
ALGORITHM = "HS256"
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
log = logging.getLogger("textileflow.auth")


def app_secret() -> str:
    return os.getenv("APP_SECRET", "change-me-in-production")


def allow_weak_secret() -> bool:
    return os.getenv("APP_ALLOW_WEAK_SECRET", "").strip().lower() in {"1", "true", "yes"}


def require_app_secret() -> str:
    secret = app_secret()
    if secret.strip() in WEAK_SECRETS:
        if not allow_weak_secret():
            raise RuntimeError(
                "APP_SECRET ainda é o valor de demonstração. Defina uma chave longa "
                "ou, só em desenvolvimento, APP_ALLOW_WEAK_SECRET=1."
            )
        log.warning(
            "APP_SECRET é o valor de demonstração. APP_ALLOW_WEAK_SECRET está ligado — "
            "não use isto na fábrica."
        )
    return secret


SECRET = app_secret()


def hash_password(value: str) -> str:
    return password_context.hash(value)


def verify_password(value: str, hashed_value: str) -> bool:
    return password_context.verify(value, hashed_value)


def issue_token(user_id: int, username: str, *, must_change: bool = False) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=12)
    return jwt.encode(
        {"sub": str(user_id), "username": username, "mcp": bool(must_change), "exp": expires},
        SECRET,
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
