from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

import numpy as np
import pandas as pd


class ColumnRole(str, Enum):
    IDENTIFIER = "identifier"
    CATEGORY = "category"
    NUMERIC_SIGNAL = "numeric_signal"
    DATETIME = "datetime"
    BOOLEAN = "boolean"
    FREE_TEXT = "free_text"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ColumnInference:
    column: str
    role: ColumnRole
    confidence: float
    unique_ratio: float
    missing_ratio: float
    reasons: tuple[str, ...]


_ID_TOKENS = {
    "id", "codigo", "code", "numero", "nro", "patente", "rut",
    "truck", "camion", "equipo", "driver", "conductor", "usuario",
    "account", "cuenta", "device", "dispositivo", "supplier",
    "proveedor", "route", "ruta", "shift", "turno", "station",
    "estacion", "node", "source", "target", "origen", "destino",
}
_TIME_TOKENS = {
    "fecha", "date", "time", "timestamp", "hora", "datetime",
}
_TEXT_TOKENS = {
    "descripcion", "description", "comentario", "comment",
    "detalle", "observacion", "notes", "nota",
}


def _normalize(name: str) -> set[str]:
    tokens = re.split(r"[^a-zA-Z0-9áéíóúñ]+", str(name).lower())
    return {token for token in tokens if token}


def infer_column_roles(frame: pd.DataFrame) -> list[ColumnInference]:
    results: list[ColumnInference] = []
    rows = max(len(frame), 1)

    for column in frame.columns:
        series = frame[column]
        tokens = _normalize(column)
        unique_ratio = float(series.nunique(dropna=True) / rows)
        missing_ratio = float(series.isna().mean())
        reasons: list[str] = []

        if pd.api.types.is_bool_dtype(series):
            role = ColumnRole.BOOLEAN
            confidence = 0.99
            reasons.append("boolean dtype")
        elif pd.api.types.is_datetime64_any_dtype(series) or tokens & _TIME_TOKENS:
            role = ColumnRole.DATETIME
            confidence = 0.92 if tokens & _TIME_TOKENS else 0.85
            reasons.append("date/time naming or dtype")
        elif pd.api.types.is_numeric_dtype(series):
            if unique_ratio > 0.95 and tokens & _ID_TOKENS:
                role = ColumnRole.IDENTIFIER
                confidence = 0.86
                reasons.append("high uniqueness and identifier-like name")
            else:
                role = ColumnRole.NUMERIC_SIGNAL
                confidence = 0.90
                reasons.append("numeric dtype")
        else:
            non_null = series.dropna().astype(str)
            avg_len = float(non_null.str.len().mean()) if not non_null.empty else 0.0
            if tokens & _ID_TOKENS or unique_ratio > 0.80:
                role = ColumnRole.IDENTIFIER
                confidence = 0.82 if tokens & _ID_TOKENS else 0.68
                reasons.append("identifier-like name or high uniqueness")
            elif tokens & _TEXT_TOKENS or avg_len > 60:
                role = ColumnRole.FREE_TEXT
                confidence = 0.82
                reasons.append("free-text naming or long values")
            elif unique_ratio < 0.30:
                role = ColumnRole.CATEGORY
                confidence = 0.80
                reasons.append("low-cardinality categorical values")
            else:
                role = ColumnRole.CATEGORY
                confidence = 0.60
                reasons.append("string/categorical fallback")

        results.append(
            ColumnInference(
                column=str(column),
                role=role,
                confidence=confidence,
                unique_ratio=unique_ratio,
                missing_ratio=missing_ratio,
                reasons=tuple(reasons),
            )
        )

    return results
