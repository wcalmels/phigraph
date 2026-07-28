from __future__ import annotations

from dataclasses import dataclass

from .database import Database


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


def default_migrations() -> tuple[Migration, ...]:
    return (
        Migration(
            1,
            "platform_core",
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS registry_records (
                record_id TEXT PRIMARY KEY,
                artifact_type TEXT NOT NULL,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                stage TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(artifact_type, name, version)
            );

            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS platform_audit (
                event_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                resource TEXT NOT NULL,
                decision TEXT NOT NULL,
                details_json TEXT NOT NULL
            );
            """,
        ),
    )


class MigrationRunner:
    def __init__(self, database: Database):
        self.database = database

    def apply(self, migrations=default_migrations()) -> list[int]:
        applied: list[int] = []
        with self.database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            existing = {
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations"
                )
            }
            for migration in sorted(migrations, key=lambda item: item.version):
                if migration.version in existing:
                    continue
                connection.executescript(migration.sql)
                connection.execute(
                    "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
                    (migration.version, migration.name),
                )
                applied.append(migration.version)
        return applied
