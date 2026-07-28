from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import ActionProposal, DecisionEffect, PolicyDecision, RuntimeMode


@dataclass(frozen=True)
class PolicyRule:
    policy_id: str
    action_types: tuple[str, ...] = ("*",)
    max_risk: str = "medium"
    allowed_modes: tuple[RuntimeMode, ...] = (RuntimeMode.REPLAY, RuntimeMode.SHADOW, RuntimeMode.COPILOT)
    require_reversible: bool = False
    required_approvals: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


_RISK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class PolicyEngine:
    def __init__(self, rules: tuple[PolicyRule, ...] | None = None):
        self.rules = rules or (
            PolicyRule("core-shadow-default", allowed_modes=(RuntimeMode.REPLAY, RuntimeMode.SHADOW)),
        )

    def evaluate(self, action: ActionProposal, *, mode: RuntimeMode, approvals: tuple[str, ...] = ()) -> PolicyDecision:
        matching = [rule for rule in self.rules if "*" in rule.action_types or action.action_type in rule.action_types]
        if not matching:
            return PolicyDecision.create(action_id=action.action_id, effect=DecisionEffect.BLOCK,
                                         policy_ids=("implicit-deny",), reasons=("no_matching_policy",))
        reasons: list[str] = []
        required: set[str] = set()
        applicable: list[str] = []
        for rule in matching:
            applicable.append(rule.policy_id)
            if mode not in rule.allowed_modes:
                reasons.append(f"mode_not_allowed:{rule.policy_id}")
            if _RISK.get(action.risk_level, 99) > _RISK.get(rule.max_risk, -1):
                reasons.append(f"risk_exceeds_limit:{rule.policy_id}")
            if rule.require_reversible and not action.reversible:
                reasons.append(f"reversibility_required:{rule.policy_id}")
            required.update(rule.required_approvals)
        missing = sorted(required - set(approvals))
        if reasons:
            effect = DecisionEffect.BLOCK
        elif missing:
            effect = DecisionEffect.REQUIRE_APPROVAL
            reasons.extend(f"missing_approval:{role}" for role in missing)
        elif mode in {RuntimeMode.REPLAY, RuntimeMode.SHADOW}:
            effect = DecisionEffect.ALLOW
            reasons.append("simulation_only")
        else:
            effect = DecisionEffect.ALLOW
        return PolicyDecision.create(action_id=action.action_id, effect=effect,
                                     policy_ids=tuple(applicable), reasons=tuple(reasons),
                                     required_approvals=tuple(sorted(required)))
