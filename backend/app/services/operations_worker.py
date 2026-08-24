"""Automatismos operacionais idempotentes: alertas, avisos e aprovisionamento."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone

from sqlalchemy import text

from ..db import SessionLocal
from ..models import Company, OperationalNotification, UserCompany
from .control_tower import refresh_alerts
from .execution import backfill_execution_ledger
from .operations_control import refresh_procurement_suggestions


log = logging.getLogger("textileflow.operations")
_stop = threading.Event()
_thread: threading.Thread | None = None
INTERVAL_SECONDS = max(30, int(os.getenv("OPERATIONS_WORKER_INTERVAL", "60")))
ADVISORY_LOCK_KEY = 1_947_001


def process_company(company_id: int) -> dict:
    db = SessionLocal()
    try:
        backfill_execution_ledger(db)
        suggestions = refresh_procurement_suggestions(db, company_id)
        # Não invoca o planeador finito: esse ponto fica deliberadamente para
        # decisão com o cliente. Apenas avalia exceções sobre dados confirmados.
        alerts = refresh_alerts(db, company_id, plan=None)
        recipients = db.query(UserCompany).filter_by(company_id=company_id).filter(
            UserCompany.role.in_(["admin", "manager", "planner", "supervisor", "quality", "warehouse"])
        ).all()
        created = 0
        now = datetime.now(timezone.utc)
        for alert in alerts:
            for membership in recipients:
                existing = db.query(OperationalNotification).filter_by(
                    operational_alert_id=alert.id, recipient_user_id=membership.user_id, channel="in_app"
                ).first()
                if existing:
                    detected = alert.detected_at
                    sent = existing.sent_at
                    if detected and sent:
                        if detected.tzinfo is None:
                            detected = detected.replace(tzinfo=timezone.utc)
                        if sent.tzinfo is None:
                            sent = sent.replace(tzinfo=timezone.utc)
                    if detected and (not sent or detected > sent):
                        existing.status = "sent"
                        existing.attempts = int(existing.attempts or 0) + 1
                        existing.sent_at = now
                        existing.error = None
                        created += 1
                    continue
                db.add(OperationalNotification(
                    company_id=company_id, operational_alert_id=alert.id,
                    recipient_user_id=membership.user_id, channel="in_app",
                    status="sent", attempts=1, sent_at=now,
                ))
                created += 1
        db.commit()
        return {"alerts": len(alerts), "notifications": created, "procurement": len(suggestions)}
    except Exception:
        db.rollback()
        log.exception("Falha nos automatismos operacionais (empresa %s)", company_id)
        return {"alerts": 0, "notifications": 0, "procurement": 0, "failed": True}
    finally:
        db.close()


def process_all_companies() -> dict:
    lock_db = SessionLocal()
    locked = True
    try:
        if lock_db.bind.dialect.name == "postgresql":
            locked = bool(lock_db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY}).scalar())
        if not locked:
            return {"companies": 0, "alerts": 0, "notifications": 0, "procurement": 0, "skipped": "worker_already_running"}
        ids = [row.id for row in lock_db.query(Company).filter(Company.active.is_(True)).all()]
        totals = {"companies": len(ids), "alerts": 0, "notifications": 0, "procurement": 0}
        for company_id in ids:
            result = process_company(company_id)
            for key in ("alerts", "notifications", "procurement"):
                totals[key] += int(result.get(key) or 0)
        return totals
    finally:
        if locked and lock_db.bind.dialect.name == "postgresql":
            lock_db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": ADVISORY_LOCK_KEY})
        lock_db.close()


def _loop() -> None:
    if _stop.wait(10):
        return
    while True:
        process_all_companies()
        if _stop.wait(INTERVAL_SECONDS):
            break


def start_operations_worker() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="operations-control", daemon=True)
    _thread.start()
    log.info("Automatismos operacionais iniciados (%ss)", INTERVAL_SECONDS)


def stop_operations_worker() -> None:
    _stop.set()
