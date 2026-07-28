from __future__ import annotations

from dataclasses import dataclass, asdict
from collections import Counter, defaultdict
import math
import pandas as pd

from .graph_builder import build_security_graph
from .schema import validate_events


SUSPICIOUS_EVENTS = {
    "privilege_change": 1.0,
    "remote_access": 0.85,
    "failed_login": 0.55,
    "process_start": 0.30,
    "data_access": 0.50,
    "login": 0.10,
}


@dataclass(frozen=True)
class CyberAlert:
    alert_id: str
    entity: str
    entity_type: str
    severity: str
    confidence: float
    anomaly_score: float
    recommendation: str
    evidence: tuple[str, ...]
    event_count: int
    first_seen: str
    last_seen: str
    executed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CyberAnalysisResult:
    validation: dict
    graph_summary: dict
    alerts: tuple[CyberAlert, ...]
    analyzed_rows: int
    executed: bool = False

    def to_dict(self) -> dict:
        return {
            "validation": self.validation,
            "graph_summary": self.graph_summary,
            "alerts": [alert.to_dict() for alert in self.alerts],
            "analyzed_rows": self.analyzed_rows,
            "executed": self.executed,
        }


class CyberShadowDetector:
    def __init__(self, *, top_k: int = 10):
        self.top_k = top_k

    def analyze(self, frame: pd.DataFrame) -> CyberAnalysisResult:
        events, validation = validate_events(frame)
        if not validation.valid:
            return CyberAnalysisResult(
                validation.to_dict(),
                {},
                (),
                len(events),
                False,
            )

        graph = build_security_graph(events)
        user_device_counts = (
            events.groupby("user_id")["device_id"]
            .nunique()
            .to_dict()
        )
        device_user_counts = (
            events.groupby("device_id")["user_id"]
            .nunique()
            .to_dict()
        )

        user_device_frequency = Counter(
            zip(events["user_id"], events["device_id"])
        )
        process_frequency = Counter(
            value
            for value in events.get(
                "process_name",
                pd.Series(dtype=object),
            ).dropna()
            if str(value).strip()
        )
        destination_frequency = Counter(
            value
            for value in events.get(
                "destination_ip",
                pd.Series(dtype=object),
            ).dropna()
            if str(value).strip()
        )

        scores: dict[tuple[str, str], list[float]] = defaultdict(list)
        evidence: dict[tuple[str, str], set[str]] = defaultdict(set)
        timestamps: dict[tuple[str, str], list[pd.Timestamp]] = defaultdict(list)

        for _, row in events.iterrows():
            risk = float(row["risk_score"])
            event_weight = SUSPICIOUS_EVENTS.get(
                str(row["event_type"]).lower(),
                0.25,
            )
            pair = (row["user_id"], row["device_id"])
            rarity = 1.0 / max(user_device_frequency[pair], 1)
            new_relationship = 1.0 if user_device_frequency[pair] == 1 else 0.0

            process = row.get("process_name")
            process_rarity = (
                1.0 / max(process_frequency[str(process)], 1)
                if pd.notna(process) and str(process).strip()
                else 0.0
            )
            destination = row.get("destination_ip")
            destination_rarity = (
                1.0 / max(destination_frequency[str(destination)], 1)
                if pd.notna(destination) and str(destination).strip()
                else 0.0
            )

            structural = min(
                1.0,
                0.35 * math.log1p(user_device_counts.get(row["user_id"], 1))
                + 0.25 * math.log1p(device_user_counts.get(row["device_id"], 1)),
            )
            score = (
                0.38 * risk
                + 0.20 * event_weight
                + 0.16 * rarity
                + 0.10 * new_relationship
                + 0.07 * process_rarity
                + 0.05 * destination_rarity
                + 0.04 * structural
            )

            for entity_type, entity_value in (
                ("user", row["user_id"]),
                ("device", row["device_id"]),
            ):
                key = (entity_type, str(entity_value))
                scores[key].append(score)
                timestamps[key].append(row["timestamp"])
                if risk >= 0.8:
                    evidence[key].add("high_source_risk")
                if new_relationship:
                    evidence[key].add("new_user_device_relationship")
                if event_weight >= 0.8:
                    evidence[key].add(str(row["event_type"]).lower())
                if process_rarity >= 1.0 and process:
                    evidence[key].add("rare_process")
                if destination_rarity >= 1.0 and destination:
                    evidence[key].add("rare_destination")
                if structural >= 0.5:
                    evidence[key].add("high_relational_centrality")

        alerts = []
        for (entity_type, entity), values in scores.items():
            peak = max(values)
            mean = sum(values) / len(values)
            combined = min(1.0, 0.7 * peak + 0.3 * mean)
            if combined < 0.35:
                continue
            severity = (
                "critical" if combined >= 0.82
                else "high" if combined >= 0.68
                else "medium" if combined >= 0.50
                else "low"
            )
            confidence = min(
                0.99,
                0.55 + 0.35 * combined
                + 0.02 * min(len(evidence[(entity_type, entity)]), 4),
            )
            recommendation = (
                "investigate_user"
                if entity_type == "user"
                else "investigate_device"
            )
            alerts.append(
                CyberAlert(
                    alert_id=f"cyber-{entity_type}-{entity}",
                    entity=entity,
                    entity_type=entity_type,
                    severity=severity,
                    confidence=round(confidence, 4),
                    anomaly_score=round(combined, 4),
                    recommendation=recommendation,
                    evidence=tuple(
                        sorted(evidence[(entity_type, entity)])
                    ),
                    event_count=len(values),
                    first_seen=min(
                        timestamps[(entity_type, entity)]
                    ).isoformat(),
                    last_seen=max(
                        timestamps[(entity_type, entity)]
                    ).isoformat(),
                    executed=False,
                )
            )

        alerts.sort(
            key=lambda item: (
                item.anomaly_score,
                item.confidence,
            ),
            reverse=True,
        )
        graph_summary = {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "users": sum(
                data.get("node_type") == "user"
                for _, data in graph.nodes(data=True)
            ),
            "devices": sum(
                data.get("node_type") == "device"
                for _, data in graph.nodes(data=True)
            ),
            "events": len(events),
        }
        return CyberAnalysisResult(
            validation.to_dict(),
            graph_summary,
            tuple(alerts[: self.top_k]),
            len(events),
            False,
        )
