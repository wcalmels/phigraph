from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class TemporalAlignment:
    table: str
    column: str
    parse_success: float
    min_time: str | None
    max_time: str | None
    suggested_granularity: str

    def to_dict(self) -> dict:
        return asdict(self)


def _granularity(series: pd.Series) -> str:
    ordered = series.dropna().sort_values()
    if len(ordered) < 2:
        return "unknown"
    median_delta = ordered.diff().dropna().median()
    seconds = median_delta.total_seconds()
    if seconds <= 60:
        return "minute"
    if seconds <= 3600:
        return "hour"
    if seconds <= 86400:
        return "day"
    if seconds <= 7 * 86400:
        return "week"
    return "month_or_more"


def infer_temporal_alignment(
    tables: Mapping[str, pd.DataFrame],
) -> list[TemporalAlignment]:
    output = []
    hints = ("fecha", "date", "time", "hora", "timestamp", "datetime")

    for name, frame in tables.items():
        for column in frame.columns:
            series = frame[column]
            name_hint = any(token in str(column).lower() for token in hints)
            dtype_hint = pd.api.types.is_datetime64_any_dtype(series)
            if not name_hint and not dtype_hint:
                continue

            parsed = pd.to_datetime(series, errors="coerce", dayfirst=True)
            success = float(parsed.notna().mean())
            if success < 0.50:
                continue
            valid = parsed.dropna()
            output.append(
                TemporalAlignment(
                    table=name,
                    column=str(column),
                    parse_success=success,
                    min_time=None if valid.empty else valid.min().isoformat(),
                    max_time=None if valid.empty else valid.max().isoformat(),
                    suggested_granularity=_granularity(valid),
                )
            )

    return output
