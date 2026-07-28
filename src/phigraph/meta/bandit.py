from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Mapping, Sequence


@dataclass(frozen=True)
class BanditArm:
    name: str
    configuration: dict
    pulls: int
    mean_reward: float


@dataclass(frozen=True)
class BanditDecision:
    selected_arm: str
    selected_configuration: dict
    exploration: bool
    score: float
    arm_scores: dict[str, float]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def ucb1_select(
    arms: Sequence[BanditArm],
    *,
    total_pulls: int,
    exploration_strength: float = 2.0,
) -> BanditDecision:
    if not arms:
        raise ValueError("At least one arm is required")

    untried = [arm for arm in arms if arm.pulls == 0]
    if untried:
        selected = untried[0]
        return BanditDecision(
            selected_arm=selected.name,
            selected_configuration=selected.configuration,
            exploration=True,
            score=float("inf"),
            arm_scores={arm.name: (float("inf") if arm.pulls == 0 else arm.mean_reward) for arm in arms},
            reasons=("untried configuration selected for exploration",),
        )

    scores = {}
    for arm in arms:
        bonus = math.sqrt(
            exploration_strength * math.log(max(total_pulls, 1)) / arm.pulls
        )
        scores[arm.name] = arm.mean_reward + bonus

    selected = max(arms, key=lambda arm: scores[arm.name])
    best_empirical = max(arms, key=lambda arm: arm.mean_reward)
    exploration = selected.name != best_empirical.name
    return BanditDecision(
        selected_arm=selected.name,
        selected_configuration=selected.configuration,
        exploration=exploration,
        score=float(scores[selected.name]),
        arm_scores={key: float(value) for key, value in scores.items()},
        reasons=(
            "UCB1 balances empirical reward and uncertainty",
            f"total_pulls={total_pulls}",
        ),
    )


def contextual_adjustment(
    base_reward: float,
    *,
    context: Mapping[str, float],
    arm_context_weights: Mapping[str, float],
) -> float:
    adjustment = sum(
        float(context.get(key, 0.0)) * float(weight)
        for key, weight in arm_context_weights.items()
    )
    return float(base_reward + adjustment)
