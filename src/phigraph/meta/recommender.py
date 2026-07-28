from __future__ import annotations
from dataclasses import dataclass, asdict
from collections import defaultdict
from .store import ExperimentRecord

@dataclass(frozen=True)
class MetaRecommendation:
    domain: str
    recommended_config: dict
    expected_score: float
    support: int
    exploration_required: bool
    reasons: tuple[str, ...]
    def to_dict(self) -> dict:
        return asdict(self)

def _key(config: dict) -> tuple:
    return (
        config.get("engineered_signal", "structural_deviation"),
        round(float(config.get("min_join_overlap", 0.25)), 2),
        int(config.get("n_null_controls", 30)),
    )

def recommend_configuration(records: list[ExperimentRecord], *, domain: str,
                            default: dict | None=None) -> MetaRecommendation:
    domain_records = [r for r in records if r.domain == domain and r.confirmed]
    if not domain_records:
        return MetaRecommendation(
            domain=domain,
            recommended_config=default or {
                "engineered_signal":"structural_deviation",
                "min_join_overlap":0.25,
                "n_null_controls":30,
            },
            expected_score=0.0, support=0, exploration_required=True,
            reasons=("no confirmed experiments for this domain",)
        )
    groups = defaultdict(list)
    for record in domain_records:
        groups[_key(record.config)].append(record)
    best_key, best_rows = max(groups.items(), key=lambda item: sum(r.score for r in item[1])/len(item[1]))
    expected = sum(r.score for r in best_rows)/len(best_rows)
    config = dict(best_rows[0].config)
    return MetaRecommendation(
        domain=domain, recommended_config=config, expected_score=float(expected),
        support=len(best_rows), exploration_required=len(best_rows)<3,
        reasons=(f"best mean score among {len(groups)} tested configurations",
                 f"supported by {len(best_rows)} confirmed runs")
    )
