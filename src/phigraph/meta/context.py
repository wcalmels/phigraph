from __future__ import annotations

from dataclasses import dataclass, asdict
import pandas as pd


@dataclass(frozen=True)
class MetaContext:
    domain: str
    table_count: int
    row_count: int
    numeric_ratio: float
    temporal_ratio: float
    missing_ratio: float

    def to_dict(self) -> dict:
        return asdict(self)


def extract_meta_context(tables: dict[str, pd.DataFrame], *, domain: str) -> MetaContext:
    total_rows = sum(len(frame) for frame in tables.values())
    total_columns = sum(len(frame.columns) for frame in tables.values())
    numeric_columns = sum(
        len(frame.select_dtypes(include="number").columns)
        for frame in tables.values()
    )
    temporal_columns = sum(
        sum(
            any(token in str(column).lower() for token in ("fecha", "date", "time", "hora", "timestamp"))
            for column in frame.columns
        )
        for frame in tables.values()
    )
    total_cells = sum(frame.size for frame in tables.values())
    missing_cells = sum(int(frame.isna().sum().sum()) for frame in tables.values())

    return MetaContext(
        domain=domain,
        table_count=len(tables),
        row_count=total_rows,
        numeric_ratio=numeric_columns / max(total_columns, 1),
        temporal_ratio=temporal_columns / max(total_columns, 1),
        missing_ratio=missing_cells / max(total_cells, 1),
    )
