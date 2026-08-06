from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.advisory.models import AdvisoryAction
from phigraph.core_v3 import CoreV3Service, EvidenceLedger, RuntimeMode
from phigraph.core_v3.api import create_core_v3_router
from phigraph.core_v3.integrations import LegacyBridge, LegacyIntegrationPaths


def test_legacy_action_maps_to_canonical_risk(tmp_path):
    bridge = LegacyBridge(
        ledger=EvidenceLedger(tmp_path / "ledger.json"),
        paths=LegacyIntegrationPaths(tmp_path / "audit.json", tmp_path / "shadow.json"),
    )
    action = bridge.action_from_advisory(
        AdvisoryAction("ticket.create", "case-1", True, 0.7, 0.7, {"queue": "security"})
    )
    assert action.risk_level == "high"
    assert action.parameters["estimated_impact"] == 0.7


def test_service_mirrors_shadow_and_policy(tmp_path):
    from phigraph.core_v3.adapters import AgentProposal, StaticAgentAdapter

    service = CoreV3Service(data_dir=tmp_path)
    report = service.run(
        adapter=StaticAgentAdapter(AgentProposal(actions=({
            "action_type": "ticket.create",
            "target": "case-1",
            "proposed_by": "test",
        },))),
        request={},
        mode=RuntimeMode.SHADOW,
    )
    assert report.executed_actions == 0
    assert len(service.bridge.audit.list()) == 1
    assert len(service.bridge.shadow.list()) == 1
    assert service.bridge.shadow.list()[0].executed is False


def test_v3_api_claim_evidence_verification_and_runtime(tmp_path):
    app = FastAPI()
    app.include_router(create_core_v3_router(tmp_path))
    client = TestClient(app)

    status = client.get("/v3/status")
    assert status.status_code == 200
    assert status.json()["version"] == "4.1.0-rc.1"

    claim = client.post("/v3/claims", json={
        "statement": "tests passed",
        "claim_type": "test_run",
        "subject": "repo",
        "issuer": "agent",
    }).json()
    evidence = client.post("/v3/evidence", json={
        "kind": "test_log",
        "source": "pytest",
        "payload": {"passed": 1},
    }).json()
    verification = client.post("/v3/verifications", json={
        "claim_id": claim["claim_id"],
        "verifier": "pytest",
        "method": "test_run",
        "result": "verified",
        "evidence_ids": [evidence["evidence_id"]],
    })
    assert verification.status_code == 201
    assert client.get(f"/v3/claims/{claim['claim_id']}").json()["status"] == "verified"

    runtime = client.post("/v3/runtime/run", json={
        "mode": "shadow",
        "actions": [{
            "action_type": "ticket.create",
            "target": "case-api",
            "proposed_by": "api-agent",
        }],
    })
    assert runtime.status_code == 200
    assert runtime.json()["executed_actions"] == 0
    assert runtime.json()["outcomes"][0]["executed"] is False
