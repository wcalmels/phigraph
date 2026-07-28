from phigraph.core_v3 import (
    ActionProposal, AgentProposal, ClaimStatus, Evidence, EvidenceLedger,
    PhiGraphCoreRuntime, PolicyEngine, PolicyRule, RuntimeMode, StaticAgentAdapter,
)


def test_ledger_verification_updates_claim(tmp_path):
    ledger = EvidenceLedger(tmp_path / "ledger.json")
    proposal = AgentProposal(claims=({
        "statement": "tests passed", "claim_type": "test_run",
        "subject": "repo", "issuer": "agent",
    },))

    def verifier(claim, context):
        return ClaimStatus.VERIFIED, [Evidence.create(
            kind="test_result", source="pytest", payload={"passed": 62, "exit_code": 0}
        )], "pytest exit code was zero"

    report = PhiGraphCoreRuntime(ledger=ledger, verifiers={"test_run": verifier}).run(
        adapter=StaticAgentAdapter(proposal), request={}, mode=RuntimeMode.SHADOW
    )
    assert report.claims[0]["status"] == "verified"
    snapshot = ledger.snapshot()
    assert snapshot["summary"]["verified_claims"] == 1
    assert snapshot["evidence"][0]["content_hash"]


def test_shadow_never_executes(tmp_path):
    ledger = EvidenceLedger(tmp_path / "ledger.json")
    proposal = AgentProposal(actions=({
        "action_type": "create_ticket", "target": "INC-1", "proposed_by": "agent",
    },))
    calls = []
    report = PhiGraphCoreRuntime(ledger=ledger).run(
        adapter=StaticAgentAdapter(proposal), request={}, mode=RuntimeMode.SHADOW,
        executor=lambda action: calls.append(action) or {"status": "done"},
    )
    assert report.executed_actions == 0
    assert calls == []
    assert report.outcomes[0]["executed"] is False


def test_guarded_auto_requires_policy_and_approval(tmp_path):
    rule = PolicyRule(
        "tickets", action_types=("create_ticket",), max_risk="low",
        allowed_modes=(RuntimeMode.GUARDED_AUTO,), required_approvals=("operations",),
    )
    ledger = EvidenceLedger(tmp_path / "ledger.json")
    runtime = PhiGraphCoreRuntime(ledger=ledger, policy_engine=PolicyEngine((rule,)))
    proposal = AgentProposal(actions=({
        "action_type": "create_ticket", "target": "INC-2", "proposed_by": "agent",
    },))
    blocked = runtime.run(adapter=StaticAgentAdapter(proposal), request={}, mode=RuntimeMode.GUARDED_AUTO)
    assert blocked.decisions[0]["effect"] == "require_approval"

    proposal2 = AgentProposal(actions=({
        "action_type": "create_ticket", "target": "INC-3", "proposed_by": "agent",
    },))
    allowed = runtime.run(
        adapter=StaticAgentAdapter(proposal2), request={}, mode=RuntimeMode.GUARDED_AUTO,
        approvals=("operations",), executor=lambda action: {"status": "created", "ticket": action.target},
    )
    assert allowed.executed_actions == 1
    assert allowed.outcomes[0]["executed"] is True
