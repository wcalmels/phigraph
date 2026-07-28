from __future__ import annotations
from dataclasses import dataclass, asdict
from time import perf_counter

@dataclass(frozen=True)
class HistoricalReplayResult:
    windows: int
    alerts: int
    accepted: int
    rejected: int
    mean_runtime_seconds: float
    results: tuple[dict, ...]
    def to_dict(self): return asdict(self)

def run_historical_replay(windows, workflow, config_factory):
    rows = []
    runtimes = []
    accepted = rejected = alerts = 0
    for index, tables in enumerate(windows):
        started = perf_counter()
        report = workflow(tables, config_factory(index))
        runtimes.append(perf_counter() - started)
        governance = report.get("artifacts", {}).get("governance", {})
        decision = governance.get("consensus", {}).get("decision", "INSUFFICIENT_EVIDENCE")
        if decision != "INSUFFICIENT_EVIDENCE":
            alerts += 1
        if decision == "ACCEPT":
            accepted += 1
        elif decision == "REJECT":
            rejected += 1
        rows.append({"window": index, "decision": decision, "report": report})
    mean_runtime = sum(runtimes) / len(runtimes) if runtimes else 0.0
    return HistoricalReplayResult(
        windows=len(rows), alerts=alerts, accepted=accepted, rejected=rejected,
        mean_runtime_seconds=float(mean_runtime), results=tuple(rows)
    )
