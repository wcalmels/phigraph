from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import uuid

from .database import Database


@dataclass(frozen=True)
class PlatformAuditEvent:
    event_id: str
    created_at: str
    actor: str
    action: str
    resource: str
    decision: str
    details: dict

    def to_dict(self) -> dict:
        return asdict(self)


class PlatformAuditStore:
    def __init__(self, database: Database):
        self.database = database

    def append(
        self,
        *,
        actor: str,
        action: str,
        resource: str,
        decision: str,
        details: dict | None = None,
    ) -> PlatformAuditEvent:
        event = PlatformAuditEvent(
            str(uuid.uuid4()),
            datetime.now(timezone.utc).isoformat(),
            actor,
            action,
            resource,
            decision,
            details or {},
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO platform_audit
                (event_id, created_at, actor, action, resource, decision, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.created_at,
                    event.actor,
                    event.action,
                    event.resource,
                    event.decision,
                    json.dumps(event.details),
                ),
            )
        return event
