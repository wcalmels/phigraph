from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ConsistencyAssessment:
    agreement_ratio: float
    shared_tokens: tuple[str, ...]
    conflicting_status_terms: tuple[str, ...]
    note: str = "Consistency is an auxiliary signal, not proof of truth."

class MultiOutputConsistencyChecker:
    _status_terms = {"passed", "failed", "blocked", "pending", "approved", "rejected"}
    def assess(self, outputs: list[str]) -> ConsistencyAssessment:
        if not outputs:
            raise ValueError("at least one output is required")
        token_sets = [self._tokens(item) for item in outputs]
        shared = set.intersection(*token_sets)
        union = set.union(*token_sets)
        ratio = 1.0 if not union else len(shared) / len(union)
        statuses = set()
        for tokens in token_sets:
            statuses.update(tokens & self._status_terms)
        return ConsistencyAssessment(
            agreement_ratio=round(ratio, 6),
            shared_tokens=tuple(sorted(shared)),
            conflicting_status_terms=tuple(sorted(statuses)) if len(statuses) > 1 else (),
        )
    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {t.lower() for t in re.findall(r"[A-Za-zÀ-ÿ0-9_]+", text) if len(t) >= 3}
