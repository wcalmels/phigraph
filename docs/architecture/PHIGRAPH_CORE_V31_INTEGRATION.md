# PhiGraph Core v3.1 — Integration Layer

## Purpose

Core v3.1 connects the canonical PhiGraph protocol to the operational capabilities retained from v2.2.3. It does not grant real-world execution authority. The release remains shadow-first and fail-closed.

## Added components

- `CoreV3Service`: application facade composing ledger, policy runtime and compatibility mirrors.
- `LegacyBridge`: adapters for advisory actions/cases and mirrors for governance audit and shadow stores.
- `/v3` FastAPI router: protocol status, claims, evidence, verification, runtime and ledger endpoints.
- Runtime event sink: emits policy and outcome events without coupling the canonical runtime to legacy modules.

## Integration flow

```text
Agent or workflow
  -> AgentAdapter
  -> Core v3 Runtime
  -> Evidence Ledger
  -> Policy Engine
  -> Runtime Outcome
  -> LegacyBridge
       -> DecisionAuditStore
       -> ShadowModeRunner
```

## Safety properties

1. `/v3/runtime/run` does not accept an external executor.
2. Replay and shadow modes cannot execute actions.
3. The default policy only permits simulation modes.
4. Missing matching policy remains an implicit deny.
5. Legacy mirroring records decisions and simulations but cannot authorize execution.

## API endpoints

- `GET /v3/status`
- `POST /v3/claims`
- `GET /v3/claims/{claim_id}`
- `POST /v3/evidence`
- `POST /v3/verifications`
- `POST /v3/runtime/run`
- `GET /v3/ledger/snapshot`

## Remaining work

- PostgreSQL event/ledger backend.
- Authenticated tenant isolation.
- Idempotency keys at the Core v3 API boundary.
- Real provider adapters under explicit policy gates.
- Canonical execution bridge to the v1.7 sandbox.
