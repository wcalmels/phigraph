from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from phigraph.hav.models import ClaimEvaluation, ClaimStatus, Verdict
from phigraph.version import HAV_POLICY_ID


@dataclass(frozen=True)
class HAVPolicyDecision:
    policy_id: str
    verdict: Verdict
    reason: str
    metadata: dict[str, Any]


class FailClosedHAVPolicy:
    policy_id = HAV_POLICY_ID

    def decide(self, *, state_available: bool, evaluations: list[ClaimEvaluation]) -> HAVPolicyDecision:
        if not state_available:
            return HAVPolicyDecision(
                self.policy_id,
                Verdict.SOURCE_UNAVAILABLE,
                "Authoritative state is unavailable; verification is blocked.",
                {},
            )
        critical_contradictions = [
            item for item in evaluations
            if item.claim.critical and item.status == ClaimStatus.CONTRADICTED
        ]
        if critical_contradictions:
            return HAVPolicyDecision(
                self.policy_id,
                Verdict.REJECT,
                "A critical claim contradicts authoritative evidence.",
                {"claim_ids": [item.claim.claim_id for item in critical_contradictions]},
            )
        critical_unknown = [
            item for item in evaluations
            if item.claim.critical and item.status in {
                ClaimStatus.UNSUPPORTED,
                ClaimStatus.INSUFFICIENT_EVIDENCE,
            }
        ]
        if critical_unknown:
            return HAVPolicyDecision(
                self.policy_id,
                Verdict.HUMAN_REVIEW,
                "A critical claim lacks sufficient evidence.",
                {"claim_ids": [item.claim.claim_id for item in critical_unknown]},
            )
        warnings = [
            item for item in evaluations
            if item.status != ClaimStatus.SUPPORTED
        ]
        if warnings:
            return HAVPolicyDecision(
                self.policy_id,
                Verdict.WARN,
                "No critical contradiction was found, but some claims are not supported.",
                {"claim_ids": [item.claim.claim_id for item in warnings]},
            )
        return HAVPolicyDecision(
            self.policy_id,
            Verdict.PASS,
            "All extracted claims are supported.",
            {},
        )
