from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

@dataclass(frozen=True)
class SLAStatus:
    breached: bool
    seconds_remaining: float
    status: str
    def to_dict(self): return asdict(self)

def evaluate_sla(sla_due_at,now=None):
    now=now or datetime.now(timezone.utc)
    due=datetime.fromisoformat(sla_due_at)
    remaining=(due-now).total_seconds()
    return SLAStatus(remaining<0,float(remaining),
                     "breached" if remaining<0 else ("at_risk" if remaining<3600 else "on_time"))
