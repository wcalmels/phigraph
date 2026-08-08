from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.core_v3.api import create_core_v3_router
from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.models import Claim


def test_hash_chain_detects_tampering(tmp_path):
    ledger = EvidenceLedger(tmp_path / "ledger.json")
    ledger.register_claim(Claim.create(statement="a", claim_type="fact", subject="x", issuer="agent"))
    ledger.register_claim(Claim.create(statement="b", claim_type="fact", subject="x", issuer="agent"))
    assert ledger.verify_chain()["valid"] is True
    payload = ledger.backend.read_all()
    payload["claims"][0]["statement"] = "tampered"
    ledger.backend.write_all(payload)
    result = ledger.verify_chain()
    assert result["valid"] is False
    assert result["reason"] == "hash_mismatch"


def test_rbac_and_oidc_ready_headers(tmp_path):
    app = FastAPI()
    app.include_router(create_core_v3_router(tmp_path, api_key="secret", trusted_identity_headers=True))
    client = TestClient(app)
    headers = {
        "X-API-Key": "secret",
        "X-Subject": "alice",
        "X-Role": "viewer",
        "X-Issuer": "oidc-proxy",
        "X-Tenant-ID": "t1",
        "X-Project-ID": "p1",
    }
    assert client.get("/v3/status", headers=headers).status_code == 200
    response = client.post("/v3/claims", headers=headers, json={
        "statement": "x", "claim_type": "fact", "subject": "s", "issuer": "alice"
    })
    assert response.status_code == 403
    assert response.json()["detail"] == "missing_permission:claim:create"


def test_health_metrics_and_integrity_endpoints(tmp_path):
    app = FastAPI()
    app.include_router(create_core_v3_router(tmp_path, allow_unauthenticated_dev=True))
    client = TestClient(app)
    assert client.get("/v3/health/live").json()["version"] == "4.1.0-rc.3"
    assert client.get("/v3/health/ready").status_code == 200
    assert client.get("/v3/ledger/integrity").json()["valid"] is True
    client.get("/v3/status")
    metrics = client.get("/v3/metrics")
    assert metrics.status_code == 200
    assert "phigraph_core_status_read" in metrics.text


def test_sqlite_concurrent_appends(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from phigraph.core_v3 import SQLiteLedgerBackend

    ledger = EvidenceLedger(backend=SQLiteLedgerBackend(tmp_path / "ledger.sqlite3", EvidenceLedger.COLLECTIONS))

    def create(index: int):
        return ledger.register_claim(Claim.create(statement=f"claim-{index}", claim_type="fact", subject="x", issuer="worker"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(create, range(20)))

    assert ledger.snapshot()["summary"]["claims"] == 20
    assert ledger.verify_chain()["valid"] is True
