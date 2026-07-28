from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import sqlite3, json, uuid

@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    created_at: str
    domain: str
    config: dict
    metrics: dict
    score: float
    confirmed: bool

class MetaLearningStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS experiments(
                experiment_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                domain TEXT NOT NULL, config TEXT NOT NULL, metrics TEXT NOT NULL,
                score REAL NOT NULL, confirmed INTEGER NOT NULL)""")

    def add(self, *, domain: str, config: dict, metrics: dict,
            score: float, confirmed: bool=False) -> ExperimentRecord:
        rec = ExperimentRecord(str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(),
                               domain, config, metrics, float(score), confirmed)
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO experiments VALUES (?,?,?,?,?,?,?)", (
                rec.experiment_id, rec.created_at, rec.domain, json.dumps(config),
                json.dumps(metrics), rec.score, int(rec.confirmed)))
        return rec

    def list(self, domain: str | None=None, confirmed_only: bool=False) -> list[ExperimentRecord]:
        sql, params, clauses = "SELECT * FROM experiments", [], []
        if domain:
            clauses.append("domain=?"); params.append(domain)
        if confirmed_only:
            clauses.append("confirmed=1")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY score DESC, created_at DESC"
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ExperimentRecord(r[0],r[1],r[2],json.loads(r[3]),json.loads(r[4]),float(r[5]),bool(r[6])) for r in rows]
