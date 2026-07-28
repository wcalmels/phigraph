from __future__ import annotations

from dataclasses import dataclass, asdict
import pandas as pd

REQUIRED_COLUMNS = (
    "timestamp",
    "user_id",
    "device_id",
    "event_type",
    "source_ip",
    "risk_score",
)

OPTIONAL_COLUMNS = (
    "destination_ip",
    "process_name",
    "resource_id",
    "alert_id",
    "privilege",
    "outcome",
)


@dataclass(frozen=True)
class CyberValidation:
    valid: bool
    rows: int
    violations: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


ALIASES = {
    "usuario": "user_id",
    "equipo": "device_id",
    "tipo_evento": "event_type",
    "ip_origen": "source_ip",
    "ip_destino": "destination_ip",
    "riesgo": "risk_score",
    "proceso": "process_name",
    "recurso": "resource_id",
}


def normalize_event_columns(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.rename(columns=ALIASES).copy()
    normalized.columns = [
        str(column).strip().lower()
        for column in normalized.columns
    ]
    return normalized


def validate_events(frame: pd.DataFrame) -> tuple[pd.DataFrame, CyberValidation]:
    frame = normalize_event_columns(frame)
    violations: list[str] = []
    warnings: list[str] = []

    for column in REQUIRED_COLUMNS:
        if column not in frame.columns:
            violations.append(f"missing_column:{column}")

    if violations:
        return frame, CyberValidation(
            False,
            len(frame),
            tuple(violations),
            tuple(warnings),
        )

    parsed = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    if parsed.isna().any():
        violations.append("invalid_timestamp")
    frame["timestamp"] = parsed

    frame["risk_score"] = pd.to_numeric(
        frame["risk_score"],
        errors="coerce",
    )
    if frame["risk_score"].isna().any():
        violations.append("invalid_risk_score")
    if (
        (frame["risk_score"] < 0)
        | (frame["risk_score"] > 1)
    ).any():
        violations.append("risk_score_out_of_range")

    for column in ("user_id", "device_id", "event_type", "source_ip"):
        if frame[column].isna().any():
            violations.append(f"null_not_allowed:{column}")

    if len(frame) < 10:
        warnings.append("small_sample")
    if frame["user_id"].nunique() < 2:
        warnings.append("single_user")
    if frame["device_id"].nunique() < 2:
        warnings.append("single_device")

    frame = frame.sort_values("timestamp").reset_index(drop=True)
    return frame, CyberValidation(
        not violations,
        len(frame),
        tuple(violations),
        tuple(warnings),
    )
