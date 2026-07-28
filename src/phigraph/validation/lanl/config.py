from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class LANLReductionConfig:
    pre_seconds: int = 3600
    post_seconds: int = 3600
    background_pre_seconds: int = 86400
    include_sources: tuple[str, ...] = (
        "auth",
        "proc",
        "flows",
        "dns",
    )
    merge_overlapping_windows: bool = True
    entity_filter: bool = True
    max_events_per_source: int | None = 500_000
    profile_name: str = "documentation-minimal"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def documentation_minimal(cls) -> "LANLReductionConfig":
        return cls(
            pre_seconds=1800,
            post_seconds=1800,
            background_pre_seconds=21600,
            include_sources=("auth", "proc", "dns"),
            entity_filter=True,
            max_events_per_source=100_000,
            profile_name="documentation-minimal",
        )

    @classmethod
    def validation_extended(cls) -> "LANLReductionConfig":
        return cls(
            pre_seconds=7200,
            post_seconds=7200,
            background_pre_seconds=86400,
            include_sources=("auth", "proc", "flows", "dns"),
            entity_filter=False,
            max_events_per_source=2_000_000,
            profile_name="validation-extended",
        )
