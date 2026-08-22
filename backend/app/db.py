import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def sqlalchemy_url(raw: str) -> str:
    url = (raw or "").strip() or "sqlite:///./textileflow.db"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    dialect = url.split("://", 1)[0]
    if dialect == "postgresql":
        url = "postgresql+psycopg://" + url.split("://", 1)[1]
    cloud = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RENDER") or os.getenv("FLY_APP_NAME"))
    want_ssl = os.getenv("DATABASE_SSL", "").strip().lower() in {"1", "true", "yes", "require"} or cloud
    if want_ssl and "sqlite" not in url and "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


DATABASE_URL = sqlalchemy_url(os.getenv("DATABASE_URL", "sqlite:///./textileflow.db"))
kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
