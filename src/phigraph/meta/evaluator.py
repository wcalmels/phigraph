from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

from .bandit import BanditArm, BanditDecision, ucb1_select
from .store import ExperimentRecord


@dataclass(frozen=True)
class ConfigurationSummary:
    name: str
    configuration: dict
    pulls: int
    mean_reward: float

    def to_dict(self) -> dict:
        return asdict(self)


def summarize_configurations(
    records: Iterable[ExperimentRecord],
    candidate_configurations: list[dict],
) -> list[ConfigurationSummary]:
    records = list(records)
    summaries: list[ConfigurationSummary] = []
    for index, config in enumerate(candidate_configurations):
        matched = [
            record for record in records
            if all(record.config.get(key) == value for key, value in config.items())
        ]
        reward = sum(record.score for record in matched) / len(matched) if matched else 0.0
        summaries.append(
            ConfigurationSummary(
                name=f"config_{index+1}",
                configuration=config,
                pulls=len(matched),
                mean_reward=float(reward),
            )
        )
    return summaries


def choose_next_configuration(
    records: Iterable[ExperimentRecord],
    candidate_configurations: list[dict],
    *,
    exploration_strength: float = 2.0,
) -> BanditDecision:
    summaries = summarize_configurations(records, candidate_configurations)
    arms = [
        BanditArm(
            name=item.name,
            configuration=item.configuration,
            pulls=item.pulls,
            mean_reward=item.mean_reward,
        )
        for item in summaries
    ]
    total_pulls = sum(arm.pulls for arm in arms)
    return ucb1_select(
        arms,
        total_pulls=max(total_pulls, 1),
        exploration_strength=exploration_strength,
    )
