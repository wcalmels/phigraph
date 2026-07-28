from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import uuid
from typing import Callable

from .database import Database


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    job_type: str
    status: str
    payload: dict
    result: dict | None
    attempts: int
    max_attempts: int
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class JobQueue:
    def __init__(self, database: Database):
        self.database = database

    def enqueue(
        self,
        *,
        job_type: str,
        payload: dict,
        max_attempts: int = 3,
    ) -> JobRecord:
        now = datetime.now(timezone.utc).isoformat()
        record = JobRecord(
            str(uuid.uuid4()),
            job_type,
            "queued",
            payload,
            None,
            0,
            max_attempts,
            now,
            now,
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs
                (job_id, job_type, status, payload_json, result_json,
                 attempts, max_attempts, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.job_id,
                    record.job_type,
                    record.status,
                    json.dumps(record.payload),
                    None,
                    record.attempts,
                    record.max_attempts,
                    record.created_at,
                    record.updated_at,
                ),
            )
        return record

    def claim_next(self) -> JobRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'queued' AND attempts < max_attempts
                ORDER BY created_at
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                UPDATE jobs
                SET status = 'running',
                    attempts = attempts + 1,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (now, row["job_id"]),
            )
            return JobRecord(
                row["job_id"],
                row["job_type"],
                "running",
                json.loads(row["payload_json"]),
                None,
                row["attempts"] + 1,
                row["max_attempts"],
                row["created_at"],
                now,
            )

    def finish(self, job_id: str, result: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = 'completed', result_json = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (json.dumps(result), now, job_id),
            )

    def fail(self, job_id: str, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT attempts, max_attempts FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            status = "failed" if row["attempts"] >= row["max_attempts"] else "queued"
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, result_json = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status, json.dumps({"error": error}), now, job_id),
            )


class Worker:
    def __init__(
        self,
        queue: JobQueue,
        handlers: dict[str, Callable[[dict], dict]],
    ):
        self.queue = queue
        self.handlers = handlers

    def run_once(self) -> JobRecord | None:
        job = self.queue.claim_next()
        if job is None:
            return None
        handler = self.handlers.get(job.job_type)
        if handler is None:
            self.queue.fail(job.job_id, "unknown_job_type")
            return job
        try:
            result = handler(job.payload)
            self.queue.finish(job.job_id, result)
        except Exception as exc:
            self.queue.fail(job.job_id, str(exc))
        return job
