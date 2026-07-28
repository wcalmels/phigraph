from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable

from .adapters import AgentAdapter
from .ledger import EvidenceLedger
from .models import ActionProposal, Claim, ClaimStatus, Evidence, Outcome, RuntimeMode, Verification
from .policy import PolicyEngine


Verifier = Callable[[Claim, dict[str, Any]], tuple[ClaimStatus, list[Evidence], str]]


@dataclass(frozen=True)
class RuntimeReport:
    mode: str
    claims: tuple[dict[str, Any], ...]
    actions: tuple[dict[str, Any], ...]
    decisions: tuple[dict[str, Any], ...]
    outcomes: tuple[dict[str, Any], ...]
    executed_actions: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PhiGraphCoreRuntime:
    """Canonical v3 orchestration facade.

    In replay and shadow modes it never executes external actions. In copiloto or
    guarded-auto modes, callers must provide an executor explicitly.
    """

    def __init__(self, *, ledger: EvidenceLedger, policy_engine: PolicyEngine | None = None,
                 verifiers: dict[str, Verifier] | None = None,
                 event_sink: Callable[[str, dict[str, Any]], None] | None = None):
        self.ledger = ledger
        self.policy_engine = policy_engine or PolicyEngine()
        self.verifiers = verifiers or {}
        self.event_sink = event_sink

    def run(self, *, adapter: AgentAdapter, request: dict[str, Any], context: dict[str, Any] | None = None,
            mode: RuntimeMode = RuntimeMode.SHADOW, approvals: tuple[str, ...] = (),
            executor: Callable[[ActionProposal], dict[str, Any]] | None = None,
            tenant_id: str = "default", project_id: str = "default") -> RuntimeReport:
        context = context or {}
        proposal = adapter.propose(request, context)
        claims: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        outcomes: list[dict[str, Any]] = []
        executed = 0

        for row in proposal.claims:
            claim = Claim.create(**row)
            self.ledger.register_claim(claim, tenant_id=tenant_id, project_id=project_id)
            verifier = self.verifiers.get(claim.claim_type)
            if verifier:
                result, evidence_rows, rationale = verifier(claim, context)
                evidence_ids = []
                for evidence in evidence_rows:
                    registered = self.ledger.register_evidence(evidence, tenant_id=tenant_id, project_id=project_id)
                    evidence_ids.append(registered.evidence_id)
                verification = Verification.create(
                    claim_id=claim.claim_id, verifier=getattr(verifier, "__name__", "verifier"),
                    method=claim.claim_type, result=result, evidence_ids=tuple(evidence_ids), rationale=rationale,
                )
                self.ledger.record_verification(verification, tenant_id=tenant_id, project_id=project_id)
            claims.append(self.ledger.get_claim(claim.claim_id))

        for row in proposal.actions:
            action = ActionProposal.create(**row)
            self.ledger.register_action(action, tenant_id=tenant_id, project_id=project_id)
            decision = self.policy_engine.evaluate(action, mode=mode, approvals=approvals)
            self.ledger.record_policy_decision(decision, tenant_id=tenant_id, project_id=project_id)
            if self.event_sink:
                self.event_sink("policy_decision", {"action": action, "decision": decision})
            actions.append(action.to_dict())
            decisions.append(decision.to_dict())

            can_execute = decision.effect.value == "allow" and mode in {RuntimeMode.COPILOT, RuntimeMode.GUARDED_AUTO}
            if can_execute and executor is not None:
                result = executor(action)
                outcome = Outcome.create(action_id=action.action_id, status=result.get("status", "completed"),
                                         executed=True, observed_effects=result)
                executed += 1
            else:
                outcome = Outcome.create(action_id=action.action_id, status="simulated", executed=False,
                                         observed_effects={"mode": mode.value, "policy_effect": decision.effect.value})
            self.ledger.record_outcome(outcome, tenant_id=tenant_id, project_id=project_id)
            if self.event_sink:
                self.event_sink("outcome", {"action": action, "decision": decision, "outcome": outcome})
            outcomes.append(outcome.to_dict())

        return RuntimeReport(mode.value, tuple(claims), tuple(actions), tuple(decisions), tuple(outcomes), executed)
