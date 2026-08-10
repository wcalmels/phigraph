import json
from pathlib import Path


def test_final_public_versions():
    from phigraph.protocol import CORE_VERSION, PROTOCOL_VERSION
    assert CORE_VERSION == "4.1.0-rc.8"
    assert PROTOCOL_VERSION == "2.0.0"


def test_verification_preserves_chain_integrity(tmp_path):
    from phigraph.core_v3.ledger import EvidenceLedger
    from phigraph.protocol import Claim, ClaimStatus, Evidence, Verification

    ledger = EvidenceLedger(tmp_path / "ledger.json")
    claim = ledger.register_claim(Claim.create(
        statement="Tests pass", claim_type="test_run", subject="repo", issuer="agent"
    ))
    evidence = ledger.register_evidence(Evidence.create(
        kind="test_log", source="pytest", payload={"exit_code": 0}
    ))
    ledger.record_verification(Verification.create(
        claim_id=claim.claim_id,
        verifier="pytest",
        method="test_run",
        result=ClaimStatus.VERIFIED,
        evidence_ids=(evidence.evidence_id,),
    ))
    result = ledger.verify_chain()
    assert result["valid"] is True
    assert result["checked"] == 3


def test_repair_legacy_ledger_chain(tmp_path):
    from phigraph.migration import repair_ledger, validate_ledger

    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({
        "claims": [{
            "claim_id": "cl_old", "statement": "x", "claim_type": "fact",
            "subject": "s", "issuer": "a", "status": "proposed",
            "confidence": None, "evidence_ids": [], "created_at": "2026-01-01T00:00:00+00:00",
            "supersedes": None, "metadata": {"tenant_id": "default", "project_id": "default"}
        }],
        "evidence": [], "verifications": [], "actions": [],
        "policy_decisions": [], "outcomes": []
    }))
    assert validate_ledger(path)["valid"] is False
    assert repair_ledger(path)["valid"] is True
    assert validate_ledger(path)["checked"] == 1


def test_protocol_v2_serialized_claim_fixture_is_stable():
    from phigraph.protocol import Claim, ClaimStatus

    expected = json.loads(Path("tests/fixtures/protocol_v2/claim.json").read_text())
    claim = Claim(
        claim_id="cl_fixture", statement="All tests pass", claim_type="test_run",
        subject="repository@commit", issuer="agent", status=ClaimStatus.VERIFIED,
        confidence=1.0, evidence_ids=("ev_fixture",),
        created_at="2026-07-27T00:00:00+00:00",
        metadata={"tenant_id": "default", "project_id": "default"},
    )
    assert claim.to_dict() == expected


def test_runtime_default_remains_shadow():
    from phigraph.protocol import RuntimeMode
    from phigraph.core_v3.runtime import PhiGraphCoreRuntime
    import inspect
    signature = inspect.signature(PhiGraphCoreRuntime.run)
    assert signature.parameters["mode"].default is RuntimeMode.SHADOW
