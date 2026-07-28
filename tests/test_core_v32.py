from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.core_v3 import Evidence, EvidenceLedger, SQLiteLedgerBackend
from phigraph.core_v3.api import create_core_v3_router


def test_sqlite_backend_persists_and_filters_scope(tmp_path):
    backend = SQLiteLedgerBackend(tmp_path / "ledger.db", EvidenceLedger.COLLECTIONS)
    ledger = EvidenceLedger(backend=backend)
    ledger.register_evidence(Evidence.create(kind="log", source="a", payload={"x": 1}), tenant_id="t1", project_id="p1")
    ledger.register_evidence(Evidence.create(kind="log", source="b", payload={"x": 2}), tenant_id="t2", project_id="p2")
    reopened = EvidenceLedger(backend=SQLiteLedgerBackend(tmp_path / "ledger.db", EvidenceLedger.COLLECTIONS))
    assert len(reopened.query("evidence", tenant_id="t1", project_id="p1")) == 1
    assert reopened.snapshot(tenant_id="t2", project_id="p2")["summary"]["evidence"] == 1


def test_evidence_hmac_integrity(tmp_path):
    ledger = EvidenceLedger(tmp_path / "ledger.json", signing_key="secret")
    evidence = ledger.register_evidence(Evidence.create(kind="test", source="pytest", payload={"passed": 70}))
    assert ledger.verify_evidence_signature(evidence.evidence_id) is True


def test_api_idempotency_scope_and_auth(tmp_path):
    app = FastAPI()
    app.include_router(create_core_v3_router(tmp_path, api_key="key", signing_key="secret"))
    client = TestClient(app)
    headers = {"x-api-key": "key", "x-tenant-id": "tenant-a", "x-project-id": "project-a", "idempotency-key": "claim-1"}
    body = {"statement": "done", "claim_type": "status", "subject": "repo", "issuer": "agent"}
    first = client.post("/v3/claims", json=body, headers=headers)
    second = client.post("/v3/claims", json=body, headers=headers)
    assert first.status_code == 201
    assert second.json()["claim_id"] == first.json()["claim_id"]
    assert client.get("/v3/ledger/claims", headers=headers).json()["count"] == 1
    assert client.get("/v3/status").status_code == 401


def test_idempotency_conflict(tmp_path):
    app = FastAPI()
    app.include_router(create_core_v3_router(tmp_path))
    client = TestClient(app)
    headers = {"idempotency-key": "same"}
    a = {"statement": "a", "claim_type": "status", "subject": "repo", "issuer": "agent"}
    b = {"statement": "b", "claim_type": "status", "subject": "repo", "issuer": "agent"}
    assert client.post("/v3/claims", json=a, headers=headers).status_code == 201
    assert client.post("/v3/claims", json=b, headers=headers).status_code == 409
