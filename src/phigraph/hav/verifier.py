from __future__ import annotations

from typing import Any

from phigraph.hav.models import (
    AuthoritativeState,
    Claim,
    ClaimEvaluation,
    ClaimStatus,
    EvidenceFact,
)


class ClaimVerifier:
    def verify(self, *, claims: list[Claim], state: AuthoritativeState) -> list[ClaimEvaluation]:
        if not state.available:
            return [
                ClaimEvaluation(
                    claim=claim,
                    status=ClaimStatus.INSUFFICIENT_EVIDENCE,
                    reason="Authoritative state source is unavailable.",
                )
                for claim in claims
            ]

        index = state.index()
        results: list[ClaimEvaluation] = []
        for claim in claims:
            direct = index.get((claim.subject, claim.predicate), [])
            if direct:
                results.append(self._compare(claim, direct))
                continue
            derived = self._derived(claim, state)
            if derived is not None:
                results.append(derived)
                continue
            results.append(ClaimEvaluation(
                claim=claim,
                status=ClaimStatus.INSUFFICIENT_EVIDENCE if claim.critical else ClaimStatus.UNSUPPORTED,
                reason="No authoritative evidence found for this claim.",
            ))
        return results

    def _compare(self, claim: Claim, facts: list[EvidenceFact]) -> ClaimEvaluation:
        supporting = [fact for fact in facts if self._equivalent(claim.value, fact.value)]
        if supporting:
            return ClaimEvaluation(
                claim=claim,
                status=ClaimStatus.SUPPORTED,
                supporting_evidence_ids=tuple(f.evidence_id for f in supporting),
                reason="Claim matches authoritative evidence.",
            )
        return ClaimEvaluation(
            claim=claim,
            status=ClaimStatus.CONTRADICTED,
            contradicting_evidence_ids=tuple(f.evidence_id for f in facts),
            reason="Claim conflicts with authoritative evidence.",
        )

    def _derived(self, claim: Claim, state: AuthoritativeState) -> ClaimEvaluation | None:
        if claim.subject == "repository" and claim.predicate == "all_required_checks_passed":
            required = [
                fact for fact in state.evidence
                if fact.subject == "repository"
                and fact.predicate.endswith("_status")
                and fact.metadata.get("required") is True
            ]
            if not required:
                return ClaimEvaluation(
                    claim=claim,
                    status=ClaimStatus.INSUFFICIENT_EVIDENCE,
                    reason="No required-check baseline is available.",
                )
            failed = [fact for fact in required if str(fact.value).lower() != "passed"]
            if failed:
                return ClaimEvaluation(
                    claim=claim,
                    status=ClaimStatus.CONTRADICTED,
                    contradicting_evidence_ids=tuple(f.evidence_id for f in failed),
                    reason="At least one required check is not passed.",
                )
            return ClaimEvaluation(
                claim=claim,
                status=ClaimStatus.SUPPORTED,
                supporting_evidence_ids=tuple(f.evidence_id for f in required),
                reason="All configured required checks are passed.",
            )

        if claim.subject == "repository" and claim.predicate == "production_ready":
            gate = [
                fact for fact in state.evidence
                if fact.subject == "repository" and fact.predicate == "release_gate_status"
            ]
            if not gate:
                return ClaimEvaluation(
                    claim=claim,
                    status=ClaimStatus.INSUFFICIENT_EVIDENCE,
                    reason="No authoritative release-gate decision is available.",
                )
            shadow_claim = Claim(
                claim_id=claim.claim_id,
                subject=claim.subject,
                predicate="release_gate_status",
                value="passed",
                text=claim.text,
                critical=True,
            )
            return self._compare(shadow_claim, gate)
        return None

    @staticmethod
    def _equivalent(left: Any, right: Any) -> bool:
        if isinstance(left, float) or isinstance(right, float):
            try:
                return abs(float(left) - float(right)) <= 1e-9
            except (TypeError, ValueError):
                return False
        return str(left).strip().lower() == str(right).strip().lower()
