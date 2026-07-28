from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import combinations
from typing import Mapping

import pandas as pd

from .entities import normalize_entity


@dataclass(frozen=True)
class JoinCandidate:
    left_table: str
    right_table: str
    left_column: str
    right_column: str
    overlap_ratio: float
    confidence: float
    cardinality: str

    def to_dict(self) -> dict:
        return asdict(self)


def _normalized_set(series: pd.Series) -> set[str]:
    return {
        normalize_entity(value)
        for value in series.dropna().astype(str)
        if normalize_entity(value)
    }


def _cardinality(left: pd.Series, right: pd.Series) -> str:
    left_unique = not left.duplicated().any()
    right_unique = not right.duplicated().any()
    if left_unique and right_unique:
        return "one_to_one"
    if left_unique and not right_unique:
        return "one_to_many"
    if not left_unique and right_unique:
        return "many_to_one"
    return "many_to_many"


def infer_join_candidates(
    tables: Mapping[str, pd.DataFrame],
    *,
    min_overlap: float = 0.25,
) -> list[JoinCandidate]:
    candidates: list[JoinCandidate] = []

    for (left_name, left), (right_name, right) in combinations(tables.items(), 2):
        for left_col in left.columns:
            left_set = _normalized_set(left[left_col])
            if not left_set:
                continue
            for right_col in right.columns:
                right_set = _normalized_set(right[right_col])
                if not right_set:
                    continue

                intersection = left_set & right_set
                denominator = min(len(left_set), len(right_set))
                overlap = len(intersection) / denominator if denominator else 0.0

                name_bonus = 0.15 if str(left_col).lower() == str(right_col).lower() else 0.0
                confidence = min(1.0, overlap + name_bonus)
                if overlap < min_overlap:
                    continue

                candidates.append(
                    JoinCandidate(
                        left_table=left_name,
                        right_table=right_name,
                        left_column=str(left_col),
                        right_column=str(right_col),
                        overlap_ratio=float(overlap),
                        confidence=float(confidence),
                        cardinality=_cardinality(left[left_col], right[right_col]),
                    )
                )

    return sorted(candidates, key=lambda item: item.confidence, reverse=True)
