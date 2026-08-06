from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.hav.api import create_hav_router


def test_api_key_optional_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("PHIGRAPH_HAV_API_KEY", raising=False)
    app = FastAPI()
    app.include_router(create_hav_router(tmp_path))
    assert TestClient(app).post("/v3/hav/factual/extract", json={"text":"Coverage 80%"}).status_code == 200

def test_api_key_enforced_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("PHIGRAPH_HAV_API_KEY", "secret")
    app = FastAPI()
    app.include_router(create_hav_router(tmp_path))
    client = TestClient(app)
    assert client.post("/v3/hav/factual/extract", json={"text":"Coverage 80%"}).status_code == 401
    assert client.post("/v3/hav/factual/extract", headers={"X-API-Key":"secret"}, json={"text":"Coverage 80%"}).status_code == 200
