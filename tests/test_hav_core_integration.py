from phigraph.core_v3.service import CoreV3Service
from phigraph.hav.adapters import repository_state
from phigraph.hav.integration import PhiGraphHAVService
from phigraph.hav.models import AuthoritativeState, Verdict


def test_hav_records_claims_evidence_verifications_and_policy(tmp_path):
    core = CoreV3Service(
        data_dir=tmp_path,
        receipt_signing_key="test-secret",
    )
    service = PhiGraphHAVService(core)
    state = repository_state(
        tests_passed=117,
        tests_total=117,
        ci_status="passed",
        codeql_status="failed",
        package_status="passed",
        docker_status="passed",
        release_gate_status="blocked",
    )

    result = service.verify_and_record(
        candidate_output="Todos los controles pasaron. El repositorio está listo para producción.",
        state=state,
        tenant_id="tuch",
        project_id="phigraph",
    )

    assert result.receipt.verdict == Verdict.REJECT
    assert result.signed_receipt["signature"]["alg"] == "hmac-sha256"

    snapshot = core.ledger.snapshot(tenant_id="tuch", project_id="phigraph")
    assert snapshot["summary"]["claims"] == 2
    assert snapshot["summary"]["verifications"] == 2
    assert snapshot["summary"]["actions"] == 1
    assert snapshot["summary"]["policy_decisions"] == 1
    assert snapshot["summary"]["evidence"] == len(state.evidence) + 1

    assert {claim["status"] for claim in snapshot["claims"]} == {"refuted"}
    assert snapshot["policy_decisions"][0]["effect"] == "block"
    assert core.ledger.verify_chain()["valid"] is True


def test_hav_fail_closed_is_persisted(tmp_path):
    core = CoreV3Service(data_dir=tmp_path)
    service = PhiGraphHAVService(core)
    state = AuthoritativeState.unavailable(
        source_system="github-actions",
        reason="API unavailable",
    )

    result = service.verify_and_record(
        candidate_output="Todos los controles pasaron.",
        state=state,
    )

    assert result.receipt.verdict == Verdict.SOURCE_UNAVAILABLE
    snapshot = core.ledger.snapshot()
    assert snapshot["policy_decisions"][0]["effect"] == "block"
    assert snapshot["claims"][0]["status"] == "unverified"
