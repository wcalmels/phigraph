from __future__ import annotations

from dataclasses import dataclass

from phigraph.hav.engine import HAVEngine
from phigraph.hav.models import AuthoritativeState


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    candidate_output: str
    state: AuthoritativeState
    expected_verdict: str
    category: str

@dataclass(frozen=True)
class BenchmarkResult:
    total: int
    correct: int
    accuracy: float
    failures: tuple[str, ...]

class BenchmarkRunner:
    def __init__(self, engine: HAVEngine | None = None) -> None:
        self.engine = engine or HAVEngine()
    def run(self, cases: list[BenchmarkCase]) -> BenchmarkResult:
        failures, correct = [], 0
        for case in cases:
            actual = self.engine.verify(candidate_output=case.candidate_output, state=case.state).verdict.value
            if actual == case.expected_verdict:
                correct += 1
            else:
                failures.append(f"{case.case_id}: expected={case.expected_verdict}, actual={actual}")
        total = len(cases)
        return BenchmarkResult(total, correct, 0.0 if total == 0 else round(correct/total, 6), tuple(failures))
