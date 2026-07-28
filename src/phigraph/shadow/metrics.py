from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np

@dataclass(frozen=True)
class ShadowMetrics:
    cases: int
    labeled_cases: int
    precision: float | None
    recall_proxy: float | None
    false_positive_rate: float | None
    operator_acceptance_rate: float | None
    mean_realized_impact: float | None
    shadow_utility: float | None
    def to_dict(self): return asdict(self)

def compute_shadow_metrics(cases, outcomes):
    by_case = {row.case_id: row for row in outcomes}
    labeled = [case for case in cases if case.case_id in by_case and by_case[case.case_id].confirmed_incident is not None]
    tp = sum(bool(by_case[c.case_id].confirmed_incident) for c in labeled)
    fp = sum(not bool(by_case[c.case_id].confirmed_incident) for c in labeled)
    precision = tp / (tp + fp) if tp + fp else None
    recall_proxy = tp / len(labeled) if labeled else None
    fpr = fp / len(labeled) if labeled else None
    reviewed = [c for c in cases if c.operator_decision != "pending"]
    accepted = [c for c in reviewed if c.operator_decision == "accepted"]
    acceptance = len(accepted) / len(reviewed) if reviewed else None
    impacts = [by_case[c.case_id].realized_impact for c in labeled
               if by_case[c.case_id].realized_impact is not None]
    mean_impact = float(np.mean(impacts)) if impacts else None
    utility = None
    if precision is not None:
        utility = float(0.5 * precision + 0.3 * (acceptance or 0.0)
                        + 0.2 * max(0.0, min(1.0, mean_impact or 0.0)))
    return ShadowMetrics(
        len(cases), len(labeled), precision, recall_proxy, fpr,
        acceptance, mean_impact, utility
    )
