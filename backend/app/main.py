import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import api_router
from .auth import require_app_secret
from .db import Base, SessionLocal, engine
from .services.primavera_worker import start_worker, stop_worker
from .services.schema import ensure_schema
from .services.seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    require_app_secret()
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    db = SessionLocal()
    try:
        seed_database(db)
    except Exception:
        db.rollback()
        import logging
        logging.getLogger("textileflow").exception("Falha ao completar dados iniciais")
    finally:
        db.close()
    start_worker()
    yield
    stop_worker()


app = FastAPI(
    title="TextileFlow AI API",
    version="1.0.0",
    description="PLM, ERP e MES têxtil configurável, do desenvolvimento à expedição.",
    lifespan=lifespan,
)
_cors = [origin.strip() for origin in os.getenv(
    "CORS_ORIGINS",
    "http://localhost:8080,http://127.0.0.1:8080,http://localhost:3000",
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok", "version": app.version}
