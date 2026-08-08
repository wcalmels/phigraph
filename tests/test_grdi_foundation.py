from __future__ import annotations

import json

from phigraph.core_v3.receipts import ReceiptSigner
from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi import (
    Approval,
    AuthorityEngine,
    AuthorizationState,
    DecisionEnvelope,
    ExecutabilityState,
    ExecutionState,
    GRDIService,
    VerificationState,
)


def _receipt(
    signer: ReceiptSigner,
    *,
    verdict: str = "PASS",
    tenant_id: str = "tenant-a",
    project_id: str = "project-a",
) -> dict:
    return signer.sign(
        {
            "receipt_id": "hav_receipt_test",
            "verdict": verdict,
            "output_hash": "abc123",
            "governance": {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "execution_authorized": False,
            },
        }
    )


def _envelope(signer: ReceiptSigner, **overrides) -> DecisionEnvelope:
    values = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "domain": "software",
        "decision_type": "promote_release",
        "subject": "phigraph@candidate",
        "proposed_by": "release-agent",
        "proposed_action": {"type": "promote", "target": "staging"},
        "hav_receipt": _receipt(signer),
        "required_authority": "verifier",
        "risk_level": "medium",
    }
    values.update(overrides)
    return DecisionEnvelope.create(**values)


def test_pass_is_verified_and_can_be_authorized_without_becoming_executable():
    signer = ReceiptSigner.create("secret")
    decision = AuthorityEngine(signer).evaluate(
        _envelope(signer),
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    assert decision.verification_state is VerificationState.VERIFIED
    assert decision.authorization_state is AuthorizationState.AUTHORIZED
    assert decision.executability_state is ExecutabilityState.NOT_EXECUTABLE
    assert decision.execution_state is ExecutionState.NOT_EXECUTED


def test_reject_and_source_unavailable_fail_closed():
    signer = ReceiptSigner.create("secret")
    for verdict in ("REJECT", "SOURCE_UNAVAILABLE"):
        envelope = _envelope(signer, hav_receipt=_receipt(signer, verdict=verdict))
        decision = AuthorityEngine(signer).evaluate(
            envelope,
            authority_subject="human-verifier",
            authority_role="verifier",
        )
        assert decision.verification_state is VerificationState.NOT_VERIFIED
        assert decision.authorization_state is AuthorizationState.NOT_AUTHORIZED
        assert f"hav_verdict_blocks:{verdict}" in decision.reasons


def test_warn_and_human_review_require_approval_but_are_not_verified():
    signer = ReceiptSigner.create("secret")
    for verdict in ("WARN", "HUMAN_REVIEW"):
        envelope = _envelope(signer, hav_receipt=_receipt(signer, verdict=verdict))
        decision = AuthorityEngine(signer).evaluate(
            envelope,
            authority_subject="human-verifier",
            authority_role="verifier",
        )
        assert decision.verification_state is VerificationState.NOT_VERIFIED
        assert decision.authorization_state is AuthorizationState.REQUIRES_APPROVAL


def test_invalid_signature_and_scope_mismatch_block():
    signer = ReceiptSigner.create("secret")
    invalid = _envelope(signer)
    invalid.hav_receipt["verdict"] = "REJECT"
    decision = AuthorityEngine(signer).evaluate(
        invalid,
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    assert decision.authorization_state is AuthorizationState.NOT_AUTHORIZED
    assert "invalid_hav_receipt_signature" in decision.reasons

    mismatch = _envelope(signer, hav_receipt=_receipt(signer, tenant_id="tenant-b"))
    decision = AuthorityEngine(signer).evaluate(
        mismatch,
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    assert decision.authorization_state is AuthorizationState.NOT_AUTHORIZED
    assert "hav_receipt_tenant_mismatch" in decision.reasons


def test_missing_signer_self_authorization_and_wrong_role_block():
    signer = ReceiptSigner.create("secret")
    envelope = _envelope(signer)
    assert AuthorityEngine(None).evaluate(
        envelope,
        authority_subject="human-verifier",
        authority_role="verifier",
    ).authorization_state is AuthorizationState.NOT_AUTHORIZED
    assert AuthorityEngine(signer).evaluate(
        envelope,
        authority_subject="release-agent",
        authority_role="verifier",
    ).authorization_state is AuthorizationState.NOT_AUTHORIZED
    assert AuthorityEngine(signer).evaluate(
        envelope,
        authority_subject="operator-a",
        authority_role="operator",
    ).authorization_state is AuthorizationState.NOT_AUTHORIZED


def test_high_risk_requires_distinct_explicit_approval():
    signer = ReceiptSigner.create("secret")
    envelope = _envelope(signer, risk_level="high")
    engine = AuthorityEngine(signer)
    review = engine.evaluate(
        envelope,
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    assert review.authorization_state is AuthorizationState.REQUIRES_APPROVAL
    approved = engine.evaluate(
        envelope,
        authority_subject="human-verifier",
        authority_role="verifier",
        approvals=(Approval("human-verifier", "verifier", True),),
    )
    assert approved.authorization_state is AuthorizationState.AUTHORIZED
    proposer_approval = engine.evaluate(
        envelope,
        authority_subject="human-verifier",
        authority_role="verifier",
        approvals=(Approval("release-agent", "verifier", True),),
    )
    assert proposer_approval.authorization_state is AuthorizationState.NOT_AUTHORIZED


def test_grdi_records_are_scoped_persistent_and_chain_valid(tmp_path):
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="secret")
    grdi = GRDIService(core)
    envelope = grdi.register_envelope(_envelope(core.receipt_signer))
    decision = grdi.authorize(
        envelope.envelope_id,
        tenant_id="tenant-a",
        project_id="project-a",
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    assert decision.authorization_state is AuthorizationState.AUTHORIZED
    assert len(core.ledger.query("decision_envelopes", tenant_id="tenant-a", project_id="project-a")) == 1
    assert len(core.ledger.query("authority_decisions", tenant_id="tenant-a", project_id="project-a")) == 1
    assert core.ledger.query("decision_envelopes", tenant_id="tenant-b") == []
    assert core.ledger.verify_chain()["valid"] is True


def test_existing_json_ledger_gains_grdi_collections_compatibly(tmp_path):
    ledger_path = tmp_path / "core_v3_ledger.json"
    ledger_path.write_text(
        json.dumps({name: [] for name in ("claims", "evidence", "verifications", "actions", "policy_decisions", "outcomes")}),
        encoding="utf-8",
    )
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="secret")
    snapshot = core.ledger.snapshot()
    assert snapshot["decision_envelopes"] == []
    assert snapshot["authority_decisions"] == []


def test_grdi_records_persist_with_sqlite_backend(tmp_path):
    core = CoreV3Service(data_dir=tmp_path, backend="sqlite", receipt_signing_key="secret")
    envelope = GRDIService(core).register_envelope(_envelope(core.receipt_signer))

    reopened = CoreV3Service(data_dir=tmp_path, backend="sqlite", receipt_signing_key="secret")
    stored = GRDIService(reopened).get_envelope(
        envelope.envelope_id,
        tenant_id="tenant-a",
        project_id="project-a",
    )

    assert stored == envelope
    assert reopened.ledger.verify_chain()["valid"] is True
