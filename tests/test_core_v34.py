import base64, hashlib, hmac, json, time
from fastapi import FastAPI
from fastapi.testclient import TestClient
from phigraph.core_v3.api import create_core_v3_router
from phigraph.core_v3.auth import JWTValidator
from phigraph.core_v3.telemetry import TraceRecorder


def token(secret, payload):
    enc=lambda obj: base64.urlsafe_b64encode(json.dumps(obj,separators=(',',':')).encode()).rstrip(b'=').decode()
    h=enc({'alg':'HS256','typ':'JWT'}); p=enc(payload)
    s=base64.urlsafe_b64encode(hmac.new(secret.encode(),f'{h}.{p}'.encode(),hashlib.sha256).digest()).rstrip(b'=').decode()
    return f'{h}.{p}.{s}'


def test_jwt_validation_and_scoped_principal():
    secret='secret'
    raw=token(secret, {'sub':'alice','role':'viewer','iss':'issuer','aud':'phi','exp':int(time.time())+60,'tenant_id':'t1','project_id':'p1'})
    principal=JWTValidator(secret,'issuer','phi').principal(raw,'default','default')
    assert principal.subject=='alice' and principal.tenant_id=='t1' and principal.role.value=='viewer'


def test_api_accepts_bearer_and_enforces_rbac(tmp_path):
    app=FastAPI(); app.include_router(create_core_v3_router(tmp_path,jwt_secret='secret',jwt_issuer='issuer',jwt_audience='phi'))
    client=TestClient(app)
    raw=token('secret', {'sub':'alice','role':'viewer','iss':'issuer','aud':'phi','exp':int(time.time())+60,'tenant_id':'t1','project_id':'p1'})
    headers={'Authorization':f'Bearer {raw}'}
    assert client.get('/v3/status',headers=headers).status_code==200
    assert client.post('/v3/claims',headers=headers,json={'statement':'x','claim_type':'fact','subject':'s','issuer':'alice'}).status_code==403
    missing_scope=token('secret', {'sub':'alice','role':'viewer','iss':'issuer','aud':'phi','exp':int(time.time())+60})
    assert client.get('/v3/status',headers={'Authorization':f'Bearer {missing_scope}'}).status_code==401


def test_sandbox_endpoint_is_dry_run(tmp_path):
    app=FastAPI(); app.include_router(create_core_v3_router(tmp_path, allow_unauthenticated_dev=True))
    client=TestClient(app)
    r=client.post('/v3/runtime/sandbox',json={'action_type':'create_ticket','target':'case-1','approvals':['alice','bob']})
    assert r.status_code==200
    body=r.json(); assert body['real_system_modified'] is False
    assert body['receipt']['executed'] is False and body['receipt']['dry_run'] is True


def test_trace_recorder_and_endpoint(tmp_path):
    recorder=TraceRecorder()
    with recorder.span('unit', key='value'):
        pass
    assert recorder.snapshot()[0]['status']=='ok'
    app=FastAPI(); app.include_router(create_core_v3_router(tmp_path, allow_unauthenticated_dev=True))
    client=TestClient(app)
    client.post('/v3/runtime/run',json={})
    response=client.get('/v3/traces')
    assert response.status_code==200 and response.json()['count'] >= 1
