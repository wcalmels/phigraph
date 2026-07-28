from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Any

import pandas as pd

from .inference import ColumnRole, infer_column_roles
from .templates import DOMAIN_TEMPLATES


@dataclass(frozen=True)
class EntityColumn:
    column: str
    entity_type: str
    confidence: float


@dataclass(frozen=True)
class RelationProposal:
    source_column: str
    target_column: str
    relation_type: str
    confidence: float


@dataclass(frozen=True)
class ModelingProposal:
    domain: str
    domain_confidence: float
    entities: tuple[EntityColumn, ...]
    relations: tuple[RelationProposal, ...]
    signal_columns: tuple[str, ...]
    weight_column: str | None
    time_column: str | None
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tokens(name: str) -> set[str]:
    return {
        token for token in re.split(r"[^a-zA-Z0-9áéíóúñ]+", str(name).lower())
        if token
    }


class AutoModelingAssistant:
    """Infer a graph model from ordinary operational tables."""

    def infer_domain(self, frame: pd.DataFrame) -> tuple[str, float]:
        columns = [str(column).lower() for column in frame.columns]
        scores: dict[str, float] = {}
        for domain, template in DOMAIN_TEMPLATES.items():
            score = 0.0
            aliases = [
                alias
                for values in template["entity_aliases"].values()
                for alias in values
            ]
            aliases += list(template["signal_aliases"])
            for column in columns:
                for alias in aliases:
                    if alias in column:
                        score += 1.0
            scores[domain] = score

        best = max(scores, key=scores.get)
        total = sum(scores.values())
        confidence = scores[best] / total if total else 0.0
        return best, confidence

    def propose(
        self,
        frame: pd.DataFrame,
        *,
        preferred_domain: str | None = None,
    ) -> ModelingProposal:
        inferences = infer_column_roles(frame)
        domain, domain_confidence = self.infer_domain(frame)
        if preferred_domain:
            domain = preferred_domain
            domain_confidence = max(domain_confidence, 0.75)

        template = DOMAIN_TEMPLATES.get(domain, DOMAIN_TEMPLATES["fleet"])
        entities: list[EntityColumn] = []
        signals: list[str] = []
        time_column: str | None = None
        warnings: list[str] = []

        for inference in inferences:
            column = inference.column
            column_lower = column.lower()
            if inference.role == ColumnRole.DATETIME and time_column is None:
                time_column = column
            if inference.role == ColumnRole.NUMERIC_SIGNAL:
                signals.append(column)

            matched_entity = None
            matched_score = 0.0
            for entity_type, aliases in template["entity_aliases"].items():
                for alias in aliases:
                    if alias in column_lower:
                        matched_entity = entity_type
                        matched_score = max(matched_score, 0.92)

            if matched_entity:
                entities.append(
                    EntityColumn(
                        column=column,
                        entity_type=matched_entity,
                        confidence=matched_score,
                    )
                )
            elif inference.role == ColumnRole.IDENTIFIER:
                entities.append(
                    EntityColumn(
                        column=column,
                        entity_type="entity",
                        confidence=max(0.55, inference.confidence - 0.10),
                    )
                )

        if len(entities) < 2:
            identifier_candidates = [
                item for item in inferences
                if item.role in {ColumnRole.IDENTIFIER, ColumnRole.CATEGORY}
            ]
            for item in identifier_candidates:
                if item.column not in {entity.column for entity in entities}:
                    entities.append(
                        EntityColumn(item.column, "entity", 0.50)
                    )
                if len(entities) >= 2:
                    break

        relations: list[RelationProposal] = []
        for i, source in enumerate(entities):
            for target in entities[i + 1:]:
                if source.column == target.column:
                    continue
                relation_type = f"{source.entity_type}_to_{target.entity_type}"
                confidence = min(source.confidence, target.confidence)
                relations.append(
                    RelationProposal(
                        source.column,
                        target.column,
                        relation_type,
                        confidence,
                    )
                )

        weight_column = None
        for candidate in signals:
            lower = candidate.lower()
            if any(token in lower for token in ("weight", "peso", "count", "conteo")):
                weight_column = candidate
                break

        if not relations:
            warnings.append("no_relations_inferred")
        if not signals:
            warnings.append("no_numeric_signal_detected")
        if domain_confidence < 0.35:
            warnings.append("domain_inference_is_weak")
        if any(entity.confidence < 0.60 for entity in entities):
            warnings.append("some_entity_types_are_generic")

        return ModelingProposal(
            domain=domain,
            domain_confidence=domain_confidence,
            entities=tuple(entities),
            relations=tuple(relations),
            signal_columns=tuple(signals),
            weight_column=weight_column,
            time_column=time_column,
            warnings=tuple(warnings),
        )

    def build_edge_table(
        self,
        frame: pd.DataFrame,
        proposal: ModelingProposal,
        *,
        relation_index: int = 0,
        signal_column: str | None = None,
    ) -> tuple[pd.DataFrame, dict[Any, float] | None]:
        if not proposal.relations:
            raise ValueError("The proposal does not contain a usable relation.")
        relation = proposal.relations[relation_index]
        columns = [relation.source_column, relation.target_column]
        if proposal.weight_column:
            columns.append(proposal.weight_column)

        edges = frame[columns].dropna(
            subset=[relation.source_column, relation.target_column]
        ).copy()
        rename = {
            relation.source_column: "source",
            relation.target_column: "target",
        }
        if proposal.weight_column:
            rename[proposal.weight_column] = "weight"
        edges = edges.rename(columns=rename)

        if "weight" not in edges.columns:
            edges["weight"] = 1.0
        else:
            edges["weight"] = pd.to_numeric(
                edges["weight"], errors="coerce"
            ).fillna(1.0)

        edges["source"] = (
            relation.source_column + ":" + edges["source"].astype(str)
        )
        edges["target"] = (
            relation.target_column + ":" + edges["target"].astype(str)
        )

        signal = None
        selected_signal = signal_column or (
            proposal.signal_columns[0] if proposal.signal_columns else None
        )
        if selected_signal and selected_signal in frame.columns:
            signal_rows = frame[
                [relation.source_column, selected_signal]
            ].dropna()
            grouped = signal_rows.groupby(relation.source_column)[selected_signal].mean()
            signal = {
                f"{relation.source_column}:{node}": float(value)
                for node, value in grouped.items()
            }

        return edges[["source", "target", "weight"]], signal
