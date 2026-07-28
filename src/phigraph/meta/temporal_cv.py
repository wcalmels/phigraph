from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Callable, Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class TemporalFold:
    train_start: int
    train_end: int
    test_start: int
    test_end: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TemporalCVResult:
    scores: tuple[float, ...]
    mean_score: float
    std_score: float
    folds: tuple[TemporalFold, ...]
    leakage_guard: bool

    def to_dict(self) -> dict:
        return {
            "scores": list(self.scores),
            "mean_score": self.mean_score,
            "std_score": self.std_score,
            "folds": [fold.to_dict() for fold in self.folds],
            "leakage_guard": self.leakage_guard,
        }


def expanding_window_folds(
    n_samples: int,
    *,
    min_train_size: int,
    test_size: int,
    step_size: int | None = None,
) -> list[TemporalFold]:
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    if min_train_size < 1 or test_size < 1:
        raise ValueError("min_train_size and test_size must be positive")

    step = step_size or test_size
    folds: list[TemporalFold] = []
    train_end = min_train_size
    while train_end + test_size <= n_samples:
        folds.append(
            TemporalFold(
                train_start=0,
                train_end=train_end,
                test_start=train_end,
                test_end=train_end + test_size,
            )
        )
        train_end += step
    return folds


def temporal_cross_validate(
    values: Sequence,
    *,
    scorer: Callable[[Sequence, Sequence], float],
    min_train_size: int,
    test_size: int,
    step_size: int | None = None,
) -> TemporalCVResult:
    folds = expanding_window_folds(
        len(values),
        min_train_size=min_train_size,
        test_size=test_size,
        step_size=step_size,
    )
    if not folds:
        raise ValueError("Not enough samples for temporal cross-validation")

    scores: list[float] = []
    leakage_guard = True
    for fold in folds:
        if fold.train_end > fold.test_start:
            leakage_guard = False
        train = values[fold.train_start:fold.train_end]
        test = values[fold.test_start:fold.test_end]
        scores.append(float(scorer(train, test)))

    array = np.asarray(scores, dtype=float)
    return TemporalCVResult(
        scores=tuple(scores),
        mean_score=float(np.mean(array)),
        std_score=float(np.std(array)),
        folds=tuple(folds),
        leakage_guard=leakage_guard,
    )
