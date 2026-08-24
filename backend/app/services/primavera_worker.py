"""Worker da fila Primavera: envia pendentes, faz retry e alerta à 3.ª falha."""

from __future__ import annotations

import logging
import threading

from sqlalchemy import text

from ..db import SessionLocal
from ..models import Company
from .primavera import flush_outbox

log = logging.getLogger("textileflow.primavera")
_stop = threading.Event()
_thread: threading.Thread | None = None
INTERVAL_SECONDS = 120
ADVISORY_LOCK_KEY = 1_947_002


def process_all_companies() -> dict:
    lock_db = SessionLocal()
    locked = True
    try:
        if lock_db.bind.dialect.name == "postgresql":
            locked = bool(lock_db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY}).scalar())
        if not locked:
            return {"sent": 0, "failed": 0, "alerts": 0, "skipped": "worker_already_running"}
        ids = [row.id for row in lock_db.query(Company.id).filter(Company.active.is_(True))]
        sent = failed = alerts = 0
        for company_id in ids:
            db = SessionLocal()
            try:
                company = db.get(Company, company_id)
                if not company:
                    continue
                cfg = dict((company.settings or {}).get("primavera") or {})
                if not (cfg.get("enabled") and cfg.get("base_url")):
                    continue
                result = flush_outbox(company)
                sent += int(result.get("sent") or 0)
                failed += int(result.get("failed") or 0)
                alerts += int(result.get("alerts") or 0)
                db.commit()
            except Exception:
                db.rollback()
                log.exception("Falha no worker Primavera (empresa %s)", company_id)
            finally:
                db.close()
        if alerts:
            log.warning("Primavera: %s documento(s) falharam 3 vezes", alerts)
        return {"sent": sent, "failed": failed, "alerts": alerts}
    finally:
        if locked and lock_db.bind.dialect.name == "postgresql":
            lock_db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": ADVISORY_LOCK_KEY})
        lock_db.close()


def _loop() -> None:
    if _stop.wait(15):
        return
    while True:
        process_all_companies()
        if _stop.wait(INTERVAL_SECONDS):
            break


def start_worker() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="primavera-outbox", daemon=True)
    _thread.start()
    log.info("Worker da fila Primavera iniciado (%ss)", INTERVAL_SECONDS)


def stop_worker() -> None:
    _stop.set()
