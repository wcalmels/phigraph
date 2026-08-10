from pathlib import Path
import pytest


def test_frozen_public_protocol_imports():
    from phigraph.protocol import Claim, Evidence, PROTOCOL_VERSION, CORE_VERSION
    assert Claim and Evidence
    assert PROTOCOL_VERSION == "2.0.0"
    assert CORE_VERSION == "4.1.0-rc.8"


def test_stable_core_and_code_namespaces():
    from phigraph.core import CoreService, CoreRuntime
    from phigraph.code import ReproducibleCorpus, PatchQualityEvaluator
    assert CoreService and CoreRuntime and ReproducibleCorpus and PatchQualityEvaluator


def test_settings_from_env_and_validation(monkeypatch, tmp_path):
    from phigraph.config import PhiGraphSettings
    monkeypatch.setenv("PHIGRAPH_BACKEND", "sqlite")
    monkeypatch.setenv("PHIGRAPH_LEDGER_PATH", str(tmp_path / "ledger.db"))
    settings = PhiGraphSettings.from_env()
    settings.validate()
    assert settings.backend == "sqlite"
    assert settings.ledger_path == tmp_path / "ledger.db"


def test_production_trusted_headers_require_oidc():
    from phigraph.config import PhiGraphSettings
    settings = PhiGraphSettings(environment="production", trusted_identity_headers=True)
    with pytest.raises(ValueError):
        settings.validate()


def test_sdk_propagates_scope_and_idempotency():
    from phigraph.sdk import PhiGraphClient
    calls = []
    class Response:
        status_code = 201
        def json(self): return {"ok": True}
    def transport(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return Response()
    client = PhiGraphClient("http://unused", tenant_id="t1", project_id="p1", transport=transport)
    assert client.create_claim({"statement": "x"}, idempotency_key="k1") == {"ok": True}
    headers = calls[0][2]["headers"]
    assert headers["X-Tenant-ID"] == "t1"
    assert headers["X-Project-ID"] == "p1"
    assert headers["Idempotency-Key"] == "k1"
