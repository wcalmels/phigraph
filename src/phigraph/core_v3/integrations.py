from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from phigraph.advisory.models import AdvisoryAction, AdvisoryCase
from phigraph.governance.audit import DecisionAuditStore
from phigraph.production.shadow import ShadowModeRunner

from .ledger import EvidenceLedger
from .models import ActionProposal, Claim, Outcome, PolicyDecision


@dataclass(frozen=True)
class LegacyIntegrationPaths:
    audit_path: Path
    shadow_path: Path


class LegacyBridge:
    """Compatibility bridge between Core v3 protocol and v2 operational stores.

    The bridge is deliberately one-way for side effects: it mirrors canonical
    records into legacy audit/shadow stores, but never grants execution authority.
    """

    def __init__(self, *, ledger: EvidenceLedger, paths: LegacyIntegrationPaths):
        self.ledger = ledger
        self.audit = DecisionAuditStore(paths.audit_path)
        self.shadow = ShadowModeRunner(paths.shadow_path)

    @staticmethod
    def action_from_advisory(action: AdvisoryAction, *, proposed_by: str = "legacy-advisory") -> ActionProposal:
        risk = "critical" if action.estimated_risk >= 0.85 else "high" if action.estimated_risk >= 0.65 else "medium" if action.estimated_risk >= 0.35 else "low"
        return ActionProposal.create(
            action_type=action.action_type,
            target=action.target,
            proposed_by=proposed_by,
            parameters={**action.parameters, "estimated_impact": action.estimated_impact, "estimated_risk": action.estimated_risk},
            reversible=action.reversible,
            risk_level=risk,
        )

    @staticmethod
    def claim_from_advisory_case(case: AdvisoryCase, *, issuer: str = "legacy-advisory") -> Claim:
        return Claim.create(
            statement=f"Advisory case {case.case_id} recommends action with governance decision {case.governance_decision}",
            claim_type="advisory_recommendation",
            subject=case.case_id,
            issuer=issuer,
            metadata={"legacy_case": case.to_dict()},
        )

    def mirror_policy_decision(self, decision: PolicyDecision, *, case_id: str, dossier: dict[str, Any] | None = None) -> dict[str, Any]:
        record = self.audit.append(
            case_id=case_id,
            decision=decision.effect.value,
            dossier=dossier or decision.to_dict(),
            approved_by="core-v3-policy-engine",
            approval_status="approved" if decision.effect.value == "allow" else "pending",
        )
        return record.to_dict()

    def mirror_shadow_outcome(self, *, action: ActionProposal, outcome: Outcome, operator_feedback: str = "") -> dict[str, Any]:
        record = self.shadow.record(
            recommendation=action.to_dict(),
            operator_feedback=operator_feedback,
            outcome=outcome.to_dict(),
        )
        return record.to_dict()
