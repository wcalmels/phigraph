from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
import sqlite3, json, uuid

@dataclass(frozen=True)
class IncidentRecord:
    incident_id: str
    created_at: str
    domain: str
    title: str
    confirmed: bool
    hotspot_nodes: tuple[str, ...]
    intervention: str
    outcome: str
    metadata: dict
    def to_dict(self) -> dict:
        return asdict(self)

class IncidentMemory:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS incidents(
                incident_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, domain TEXT NOT NULL,
                title TEXT NOT NULL, confirmed INTEGER NOT NULL, hotspot_nodes TEXT NOT NULL,
                intervention TEXT NOT NULL, outcome TEXT NOT NULL, metadata TEXT NOT NULL)""")

    def add(self, *, domain: str, title: str, confirmed: bool, hotspot_nodes: list[str],
            intervention: str, outcome: str, metadata: dict|None=None) -> IncidentRecord:
        rec = IncidentRecord(str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(),
                             domain, title, confirmed, tuple(hotspot_nodes),
                             intervention, outcome, metadata or {})
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?,?)", (
                rec.incident_id, rec.created_at, rec.domain, rec.title, int(rec.confirmed),
                json.dumps(rec.hotspot_nodes), rec.intervention, rec.outcome, json.dumps(rec.metadata)))
        return rec

    def search(self, query: str="", *, confirmed_only: bool=False) -> list[IncidentRecord]:
        sql, params, clauses = "SELECT * FROM incidents", [], []
        if query:
            clauses.append("(title LIKE ? OR domain LIKE ? OR intervention LIKE ? OR outcome LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like, like, like])
        if confirmed_only:
            clauses.append("confirmed=1")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [IncidentRecord(r[0],r[1],r[2],r[3],bool(r[4]),tuple(json.loads(r[5])),
                               r[6],r[7],json.loads(r[8])) for r in rows]
