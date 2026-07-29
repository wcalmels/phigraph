from __future__ import annotations

from phigraph.hav.extraction.hybrid import HybridClaimExtractor
from phigraph.hav.extractor import RuleBasedClaimExtractor
from phigraph.hav.models import AuthoritativeState, HAVReceipt
from phigraph.hav.policy import FailClosedHAVPolicy
from phigraph.hav.verifier import ClaimVerifier


class HAVEngine:
    def __init__(
        self,
        *,
        extractor: RuleBasedClaimExtractor | HybridClaimExtractor | None = None,
        verifier: ClaimVerifier | None = None,
        policy: FailClosedHAVPolicy | None = None,
    ) -> None:
        self.extractor = extractor or HybridClaimExtractor()
        self.verifier = verifier or ClaimVerifier()
        self.policy = policy or FailClosedHAVPolicy()

    def verify(self, *, candidate_output: str, state: AuthoritativeState) -> HAVReceipt:
        claims = self.extractor.extract(candidate_output)
        evaluations = self.verifier.verify(claims=claims, state=state)
        decision = self.policy.decide(
            state_available=state.available,
            evaluations=evaluations,
        )
        return HAVReceipt.create(
            state_id=state.state_id,
            verdict=decision.verdict,
            evaluations=evaluations,
            policy_decisions=[{
                "policy_id": decision.policy_id,
                "verdict": decision.verdict.value,
                "reason": decision.reason,
                "metadata": decision.metadata,
            }],
            candidate_output=candidate_output,
        )
