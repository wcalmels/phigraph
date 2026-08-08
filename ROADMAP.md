# PhiGraph Roadmap

## In progress: v4.1 — GRDI Foundation (development candidate)

- **Done (integration branch):** canonical HAV v0.2, Core identity for HAV, idempotent `/v3/hav/verify`, versioned policy receipts
- **Next:** Decision Envelope, Authority Engine boundary, Execution Gateway stub, Outcome Ledger stub
- **Not started:** full GRDI runtime, production 4.1.0 stable release

See `PROJECT_STATUS.md`, `docs/architecture/PHIGRAPH_HAV_INTEGRATION.md`, ADR-014/015.

## Completed: Core v3.5

Federated OIDC/JWKS identity, W3C tracing, OTLP-ready export, signed receipts, rate limiting, RLS scope hooks and process-isolated dry-run sandbox.

## Proposed: Core v3.6

- OIDC discovery and background JWKS rotation
- distributed rate limiting
- asymmetric receipt signatures and key management
- hardened container sandbox
- PostgreSQL integration tests in CI
- agent benchmark harness for PhiGraph Code


## Completed — Core v3.2
- Backend abstraction and SQLite persistence
- Scoped tenant/project records
- Idempotent and optionally authenticated API
- Evidence integrity signatures
- Scoped query and pagination endpoints

## Next — Core v3.3
- PostgreSQL backend and migrations
- OAuth2/OIDC and RBAC enforcement
- append-only hash chaining and key rotation
- canonical controlled-execution bridge
- concurrency and load testing

# PhiGraph Roadmap

## Completed — Core v3.1 Integration
- Canonical runtime connected to governance audit and shadow records.
- FastAPI v3 protocol surface.
- Legacy advisory compatibility mapping.
- 68-test regression baseline.

## Next — Core v3.2 Persistence & Execution Bridge
- Abstract ledger backend interface.
- PostgreSQL implementation and migrations.
- Idempotent API commands.
- Controlled bridge to existing dry-run execution sandbox.
- Signed evidence envelopes.

## v3.0.0 — Canonical Core Foundation

**Status:** implemented in this package.

- Canonical evidence and action protocol.
- Evidence Ledger with deterministic hashes.
- Verification registry.
- Provider-neutral Agent Adapter API.
- Policy Engine with implicit deny.
- Replay, shadow, copilot and guarded-auto runtime modes.
- Compatibility layer preserving v2.2.3 packages.
- Initial ADR discipline and regression tests.

## v3.1 — Core Integration

- Map existing governance dossiers into canonical Claims and Evidence.
- Adapt existing shadow cases to canonical Actions and Outcomes.
- Bridge ControlledExecutionSandbox through the v3 executor interface.
- Add JSON Schema files and protocol conformance tests.
- Add FastAPI endpoints for claims, evidence, verification and authorization.

## v3.2 — PhiGraph Code MVP

- Repository, requirement, commit and test-run domain model.
- Git and pytest verifiers.
- Claim extraction for completion and regression statements.
- Shadow benchmark: model alone versus model plus PhiGraph.
- Local agent with BYOK/provider-neutral model adapters.

## v3.3 — Enterprise Hardening

- PostgreSQL-backed ledger and migrations.
- Tenant and workspace boundaries.
- OIDC/SSO, RBAC and secrets management.
- Signed evidence receipts and retention policies.
- Load, fault-injection and recovery tests.

## v3.4 — Domain Convergence

- Cyber package migrated to the canonical protocol.
- Logistics and Cost Control packages.
- Shared domain-pack SDK and connector contract.
- Cross-domain corridor and impact analysis.

## v4 research track

- Graph-augmented memory and context engine.
- Multi-model routing based on risk and evidence coverage.
- Hypothesis lifecycle and causal-assumption registry.
- Federated/edge evidence processing.

## Release gate

A version is not considered complete solely because code exists. Each release requires:

1. all regression tests pass;
2. claims are backed by reproducible artifacts;
3. compatibility changes are documented;
4. security-relevant defaults are fail-closed;
5. benchmark limitations are explicit.
### After v3.4
- Asymmetric OIDC/JWKS validation and key rotation.
- OpenTelemetry exporter integration and distributed context propagation.
- Transaction-local PostgreSQL RLS scope enforcement in backend code.
- Signed execution receipts and approved real connectors under separate safety review.


## v3.6 — PhiGraph Code benchmark (completed)
- Deterministic repository index
- Evidence-gated compile/test verification
- Baseline vs governed comparison
- GitHub-ready repository descriptor

## v3.7 — Model and GitHub integrations
- GitHub App/read-only connector
- task corpus and mutation benchmark
- model adapter experiments
- statistical benchmark reports

## v3.7 — Code validation completed
- Read-only GitHub connector.
- Reproducible multimodel benchmark suites.
- Automated research reports.
- Extended allow-listed verification.

## Next: v3.8
- GitHub App authentication and webhook-free snapshot import.
- Issue-to-requirement graph and pull-request evidence graph.
- Model adapter interface for real LLM providers and local models.
- Controlled patch proposal format without remote writes.
- Statistical benchmark corpus and confidence intervals.

## Completed in v3.8
- Commit-bound repository snapshots and deterministic tree hashes.
- Explicit requirement trace graph.
- Provider-neutral model adapter contract.
- Patch evaluation in disposable repository copies.
- Benchmark confidence intervals and statistical summaries.

## Candidate v3.9
- GitHub App read-only authentication and archived commit download.
- Real provider adapters with cost/latency capture.
- Reproducible task corpus and repeated trials.
- Coverage, security, and dependency verification.

## After v3.9

- v4.0 candidate: freeze Protocol v2 and stabilize public SDK/API.
- Add signed asymmetric experiment manifests and KMS-backed credentials.
- Add real GitHub App installation flow and commit provenance verification.
- Add broader SAST/SCA integrations and benchmark datasets with published methodology.
- Run controlled model comparisons with confidence intervals and preregistered acceptance criteria.

## v4.0 General Availability exit criteria

- Run published multi-model PhiGraph Code benchmark on a versioned corpus.
- Validate PostgreSQL/RLS and OIDC/JWKS in integration CI.
- Add compatibility fixtures for Protocol v2 serialized records.
- Complete security review and deployment runbook.
- Freeze supported Python and dependency matrix.
- Confirm upgrade path from 3.9.0 to 4.0.0 without ledger loss.
