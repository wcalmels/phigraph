import base64
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.core_v3.api import create_core_v3_router
from phigraph.core_v3.auth import JWKSCache, OIDCValidator
from phigraph.core_v3.rate_limit import SlidingWindowRateLimiter
from phigraph.core_v3.receipts import ReceiptSigner
from phigraph.core_v3.telemetry import TraceContext, TraceRecorder


def _b64int(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_oidc_jwks_validation_and_cache():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private.public_key().public_numbers()
    jwks = {"keys": [{"kty": "RSA", "kid": "k1", "alg": "RS256", "use": "sig", "n": _b64int(numbers.n), "e": _b64int(numbers.e)}]}
    calls = []
    cache = JWKSCache(fetcher=lambda url: calls.append(url) or jwks)
    validator = OIDCValidator("https://issuer/jwks", "https://issuer", "phi", cache=cache)
    token = jwt.encode({"sub": "alice", "role": "viewer", "iss": "https://issuer", "aud": "phi", "exp": int(time.time()) + 60}, private, algorithm="RS256", headers={"kid": "k1"})
    assert validator.principal(token, "t", "p").subject == "alice"
    validator.validate(token)
    assert len(calls) == 1


def test_w3c_trace_context_is_propagated():
    recorder = TraceRecorder()
    incoming = TraceContext.parse("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
    with recorder.use_context(incoming):
        with recorder.span("child"):
            pass
    row = recorder.snapshot()[0]
    assert row["trace_id"] == incoming.trace_id
    assert row["parent_span_id"] == incoming.parent_span_id


def test_signed_receipt_detects_tampering():
    signer = ReceiptSigner.create("secret")
    signed = signer.sign({"request_id": "r1", "status": "simulated", "executed": False})
    assert signer.verify(signed)
    signed["status"] = "executed"
    assert not signer.verify(signed)


def test_rate_limiter_blocks_excess_requests(tmp_path):
    app = FastAPI()
    app.include_router(create_core_v3_router(tmp_path, rate_limit=2, rate_window_seconds=60))
    client = TestClient(app)
    assert client.get("/v3/status").status_code == 200
    assert client.get("/v3/status").status_code == 200
    response = client.get("/v3/status")
    assert response.status_code == 429 and response.headers["retry-after"]


def test_api_oidc_trace_and_signed_sandbox(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private.public_key().public_numbers()
    jwks = {"keys": [{"kty": "RSA", "kid": "k1", "alg": "RS256", "use": "sig", "n": _b64int(numbers.n), "e": _b64int(numbers.e)}]}
    token = jwt.encode({"sub": "alice", "role": "admin", "iss": "https://issuer", "aud": "phi", "exp": int(time.time()) + 60}, private, algorithm="RS256", headers={"kid": "k1"})
    app = FastAPI()
    app.include_router(create_core_v3_router(tmp_path, oidc_jwks_url="https://issuer/jwks", oidc_issuer="https://issuer", oidc_audience="phi", oidc_jwks_fetcher=lambda _: jwks, receipt_signing_key="receipt-key"))
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}", "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
    response = client.post("/v3/runtime/sandbox", headers=headers, json={"action_type": "create_ticket", "target": "case-1", "approvals": ["a", "b"]})
    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["signature"]["alg"] == "hmac-sha256"
    assert client.post("/v3/receipts/verify", headers={"Authorization": f"Bearer {token}"}, json=receipt).json()["valid"] is True
    assert client.get("/v3/traces", headers={"Authorization": f"Bearer {token}"}).json()["items"][-1]["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
