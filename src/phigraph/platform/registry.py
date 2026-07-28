from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import uuid

from .database import Database


@dataclass(frozen=True)
class RegistryRecord:
    record_id: str
    artifact_type: str
    name: str
    version: str
    stage: str
    metadata: dict
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class ArtifactRegistry:
    VALID_TYPES = {"model", "kernel", "workflow", "dataset"}
    VALID_STAGES = {"experimental", "shadow", "staging", "production", "archived"}

    def __init__(self, database: Database):
        self.database = database

    def register(
        self,
        *,
        artifact_type: str,
        name: str,
        version: str,
        stage: str = "experimental",
        metadata: dict | None = None,
    ) -> RegistryRecord:
        if artifact_type not in self.VALID_TYPES:
            raise ValueError("Unsupported artifact type.")
        if stage not in self.VALID_STAGES:
            raise ValueError("Unsupported registry stage.")
        record = RegistryRecord(
            str(uuid.uuid4()),
            artifact_type,
            name,
            version,
            stage,
            metadata or {},
            datetime.now(timezone.utc).isoformat(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO registry_records
                (record_id, artifact_type, name, version, stage, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.artifact_type,
                    record.name,
                    record.version,
                    record.stage,
                    json.dumps(record.metadata),
                    record.created_at,
                ),
            )
        return record

    def list(self, *, artifact_type: str | None = None) -> list[RegistryRecord]:
        sql = "SELECT * FROM registry_records"
        params: list[object] = []
        if artifact_type:
            sql += " WHERE artifact_type = ?"
            params.append(artifact_type)
        sql += " ORDER BY created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [
            RegistryRecord(
                row["record_id"],
                row["artifact_type"],
                row["name"],
                row["version"],
                row["stage"],
                json.loads(row["metadata_json"]),
                row["created_at"],
            )
            for row in rows
        ]

    def promote(self, record_id: str, stage: str) -> None:
        if stage not in self.VALID_STAGES:
            raise ValueError("Unsupported registry stage.")
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE registry_records SET stage = ? WHERE record_id = ?",
                (stage, record_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(record_id)
