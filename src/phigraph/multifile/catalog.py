from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping

import pandas as pd

from phigraph.modeling import AutoModelingAssistant
from phigraph.modeling.inference import infer_column_roles


@dataclass(frozen=True)
class TableProfile:
    name: str
    rows: int
    columns: int
    domain: str
    domain_confidence: float
    column_roles: tuple[dict, ...]
    entity_columns: tuple[str, ...]
    signal_columns: tuple[str, ...]
    time_columns: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FileCatalog:
    tables: tuple[TableProfile, ...]

    def to_dict(self) -> dict:
        return {"tables": [table.to_dict() for table in self.tables]}


def profile_tables(tables: Mapping[str, pd.DataFrame]) -> FileCatalog:
    assistant = AutoModelingAssistant()
    profiles = []

    for name, frame in tables.items():
        proposal = assistant.propose(frame)
        roles = infer_column_roles(frame)
        profiles.append(
            TableProfile(
                name=name,
                rows=int(len(frame)),
                columns=int(len(frame.columns)),
                domain=proposal.domain,
                domain_confidence=float(proposal.domain_confidence),
                column_roles=tuple(
                    {
                        "column": item.column,
                        "role": item.role.value,
                        "confidence": item.confidence,
                        "unique_ratio": item.unique_ratio,
                        "missing_ratio": item.missing_ratio,
                    }
                    for item in roles
                ),
                entity_columns=tuple(entity.column for entity in proposal.entities),
                signal_columns=tuple(proposal.signal_columns),
                time_columns=tuple(
                    item.column for item in roles if item.role.value == "datetime"
                ),
            )
        )

    return FileCatalog(tuple(profiles))
