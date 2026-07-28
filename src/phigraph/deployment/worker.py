from __future__ import annotations

import time

from phigraph.platform import (
    Database,
    DatabaseSettings,
    JobQueue,
    MigrationRunner,
    Worker,
)

from .config import load_settings


def _shadow_handler(payload: dict) -> dict:
    return {
        "accepted": True,
        "mode": "shadow",
        "executed": False,
        "payload_keys": sorted(payload),
    }


def main() -> None:
    settings = load_settings()
    database_url = getattr(
        settings,
        "database_url",
        "sqlite:///data/phigraph.db",
    )
    database = Database(DatabaseSettings(database_url))
    MigrationRunner(database).apply()
    worker = Worker(
        JobQueue(database),
        handlers={"shadow_analysis": _shadow_handler},
    )
    while True:
        job = worker.run_once()
        if job is None:
            time.sleep(1.0)
