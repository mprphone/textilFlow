"""Worker autónomo: fila Primavera + automatismos operacionais."""

from __future__ import annotations

import logging
import time

from .auth import require_app_secret
from .logging_setup import configure_logging
from .services.operations_worker import INTERVAL_SECONDS as OPS_INTERVAL
from .services.operations_worker import process_all_companies as process_operations
from .services.primavera_worker import INTERVAL_SECONDS as PRI_INTERVAL
from .services.primavera_worker import process_all_companies as process_primavera

log = logging.getLogger("textileflow.worker")


def main() -> None:
    configure_logging()
    require_app_secret()
    interval = min(PRI_INTERVAL, OPS_INTERVAL)
    log.info("Worker autónomo iniciado (intervalo %ss)", interval)
    while True:
        try:
            process_primavera()
        except Exception:
            log.exception("Falha no ciclo Primavera")
        try:
            process_operations()
        except Exception:
            log.exception("Falha no ciclo operacional")
        time.sleep(interval)


if __name__ == "__main__":
    main()
