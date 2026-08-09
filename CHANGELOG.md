# Changelog

## 4.1.0-rc.5 - 2026-08-08 (development candidate)

- Added deterministic GRDI Replay Audit engine over the persisted shadow chain.
- Added signed `ReplayReport` and `HistoricalComparison` records with fail-closed validation.
- Added `/v4/grdi/execution-plans/{plan_id}/replays` and replay comparison endpoints.
- Enforced replay invariants: no simulation rerun, execution, connectors, or external effects.
- Added ADR-019, replay protocol, conformance report and release notes.

## 4.1.0-rc.4 - 2026-08-08 (development candidate)

- Added immutable Shadow Outcome Ledger fed only by validated simulation receipts.
- Added deterministic effect assessment aggregation and signed outcome records.
- Added `/v4/grdi/execution-plans/{plan_id}/outcomes` and outcome read endpoints.
- Enforced one outcome per `shadow_receipt_id` with in-process atomicity.
- Added ADR-018, outcome protocol, conformance report and release notes.

## 4.1.0-rc.3 - 2026-08-08 (development candidate)

- Added shadow Execution Gateway for auditable execution plans without external effects.
- Added `ExecutionRequest`, `GatewayDecision`, and `ShadowExecutionReceipt` ledger records.
- Added `/v4/grdi/execution-plans` create/read/simulate endpoints with scoped idempotency.
- Added signed shadow receipts verifiable by Core receipt signer.
- Kept authority decisions non-executable and non-executed; no connector dispatch.
- Added ADR-017, gateway protocol, shadow conformance report and release notes.

## 4.1.0-rc.2 - 2026-08-08 (development candidate)

- Added GRDI Decision Envelope and Authority Decision contracts.
- Added fail-closed Authority Engine over signed, scoped HAV receipts.
- Persisted GRDI records in the tamper-evident Core ledger.
- Added scoped idempotent `/v4/grdi` endpoints.
- Kept all authorized decisions non-executable and non-executed.
- Added GRDI protocol, ADR, release notes and conformance tests.

## 4.1.0-rc.1 - 2026-08-06 (development candidate)

- Integrated HAV v0.2 as canonical verification component (`phigraph.hav`).
- Added `/v3/hav/verify`, `/v3/hav/factual/extract`, `/v3/hav/consistency` to deployment app.
- Reused Core authentication, RBAC (`hav:verify`), rate limits and idempotency for HAV.
- Removed tenant/project from public HAV verify body; scope comes from authenticated identity.
- Centralized version constants (`HAV_VERSION`, policy IDs, verifier ID).
- Added governance-enriched signed receipts with GRDI boundary metadata.
- Added canonical integration tests (146 total passing in integration session).

## 3.6.0 - 2026-07-27

- Added PhiGraph Code repository indexer and deterministic symbol inventory.
- Added allow-listed compile and pytest verification.
- Added baseline-versus-governed benchmark with false-completion blocking.
- Added `/v3/code/index` and `/v3/code/benchmark`.
- Added provider-neutral GitHub repository descriptor.
- Expanded verified suite to 91 passing tests.


## 3.5.0 - 2026-07-27

- Added OIDC/JWKS RS256 and ES256 validation with cache and key refresh.
- Added W3C trace-context propagation and optional OTLP/HTTP export.
- Added HMAC-signed dry-run execution receipts and verification endpoint.
- Added per-principal sliding-window rate limiting.
- Added PostgreSQL transaction scope hooks for RLS.
- Added optional child-process isolation for the dry-run sandbox.
- Verified 85 passing tests.


## 3.4.0 - 2026-07-27

- Added backend-neutral Evidence Ledger contract.
- Added durable SQLite backend.
- Added tenant/project scoping and ledger query API.
- Added HMAC-SHA256 evidence integrity signatures.
- Added idempotency keys with payload-conflict detection.
- Added optional API-key authentication.
- Preserved shadow-first execution-disabled API behavior.


## 3.1.0 - 2026-07-27

### Added
- CoreV3Service application facade.
- LegacyBridge for advisory, governance audit and shadow-store interoperability.
- Runtime event sink for policy decisions and outcomes.
- FastAPI `/v3` protocol endpoints for claims, evidence, verification, runtime and ledger snapshots.
- Core v3.1 architecture documentation and ADR-003.
- Integration and API regression tests.

### Safety
- The public v3 runtime endpoint remains non-executing.
- Legacy mirrors cannot authorize external actions.
- Default policy remains shadow/replay-only and fail-closed.

## 3.0.0 - 2026-07-27

### Added
- Canonical Core v3 protocol for claims, evidence, verification, actions, policy decisions and outcomes.
- Append-oriented Evidence Ledger with SHA-256 payload hashes and atomic writes.
- Provider-neutral Agent Adapter API.
- Policy Engine with implicit deny, risk limits, mode constraints and approval gates.
- Governed runtime supporting replay, shadow, copilot and guarded-auto modes.
- Architecture, protocol documentation and initial ADR records.
- Core v3 regression tests while retaining all v2.2.3 packages.

### Compatibility
- Existing v2.2.3 modules remain import-compatible. Core v3 is exposed through `phigraph.core_v3`.


## 2.2.3

- LANL heterogeneous temporal graph builder.
- User, computer and process nodes with multi-source relations.
- GraphML, node, edge, anomaly and attack-path exports.
- Interpretable relational scoring and fixture validation.


## 2.2.2

- Reproducible LANL cyber1 reduction toolkit.
- Streaming selection around red-team events.
- Minimal documentation and extended validation profiles.
- Cross-source schemas, provenance, checksums and source-line lineage.
- Illustrative fixture and generated reduced example.


## 2.2.1

- First external CIC-IDS2017 validation.
- Reproducible benign-reference benchmark protocol.
- Comparison with robust z-score, Isolation Forest and LOF.
- Validation metrics, predictions and limitations report.


## 2.2.0

- Operational cybersecurity shadow MVP.
- CSV and JSON event ingestion.
- Security graph construction and relational anomaly scoring.
- Analyst dashboard and feedback registry.
- Accumulated precision and false-positive metrics.
- Synthetic attack-chain demonstration dataset.
- Dedicated API, Dockerfile and Compose deployment.


## 2.1.0

- General platform SDK and dynamic domain registry.
- Domain manifests, contracts, normalization and graph mappings.
- Cybersecurity, fleet, maintenance, fraud and mining packs.
- Domain discovery and preparation API.


## 2.0.0

- Production learning platform services.
- Database migrations and relational persistence.
- Model and kernel artifact registry.
- Persistent jobs and worker runtime.
- Role-based access control and platform audit.
- Governed staging promotion with production blocked.
- Staging Docker Compose configuration.


## 1.9.0

- Shadow-only FastAPI deployment service.
- Health, readiness and configuration endpoints.
- Environment validation and request-size limits.
- Docker and Docker Compose packaging.
- Non-root and read-only container configuration.
- GitHub Actions CI and Docker build.


## 1.8.0

- Reliability and observability.
- Health checks, metrics, traces, circuit breakers, retries and limits.


## 1.7.0

- Controlled execution sandbox.
- Fake ticket and monitoring connectors.
- Dry-run enforcement and idempotency.
- Dual approval and rollback-plan validation.
- Simulated execution and rollback receipts.


## 1.6.0

- Controlled advisory queue.
- Explicit review and approval records.
- SLA monitoring and permission policies.
- Reversible-action simulation.
- Governed maturity promotion checks.


## 1.5.0

- Shadow deployment workflow.
- Historical replay runner.
- Operator feedback and delayed outcome registry.
- Shadow precision, false-positive, acceptance and utility metrics.
- Non-execution guarantee for shadow recommendations.


## 1.4.0

- Agent governance policy and weighted consensus.
- Required-agent validation and veto authority.
- Contradiction detection.
- Human review dossier and persistent decision audit.


## 1.3.0

- Production readiness workflow.
- Data contracts and drift detection.
- Kernel ensemble critic and score calibration.
- Evidence fusion and safety gate.
- Production readiness scoring and shadow mode registry.


## 1.2.0

- Context-aware kernel meta-learning.
- Joint kernel and hyperparameter search.
- Confirmed kernel experiment store.
- Context-similarity weighted exploration.


## 1.1.0

- Adaptive kernel registry.
- Multiplex, temporal, heat, signal-aware, non-backtracking and edge kernels.
- KernelSelectionAgent and KernelUncertaintyAgent.
- Kernel ablation benchmark.


## 1.0.0

- Formal reproducible benchmark framework.
- Synthetic fleet and fraud datasets with known causes.
- Isolation Forest, LOF, One-Class SVM and robust z-score baselines.
- Detection and causal-localization metrics.
- Runtime and stability reporting.
- JSON, CSV and Markdown benchmark reports.
- Benchmark CLI and web tab.


## 0.9.0

- Expanding-window temporal cross-validation.
- Explicit temporal leakage guard.
- UCB1 contextual configuration selector.
- Controlled exploration of untested configurations.
- Advanced meta-learning workflow and web tab.


## 0.8.0

- MetaLearningAgent.
- Composite performance scoring.
- SQLite experiment history.
- Domain-specific configuration recommendation.
- Operational and meta-learning web tab.


## 0.7.0

- RecommendationAgent.
- OutcomeLearningAgent.
- Ranked recommendations.
- Intervention registry.
- Before/after evaluation.
- SQLite incident memory.


## 0.6.0

- ProjectionAgent for heterogeneous graph projections.
- SignalEngineeringAgent with auditable formulas.
- ModelSelectionAgent for Laplacian and mode selection.
- ProjectedRootCauseAgent.
- NullControlAgent using degree-preserving rewiring.
- AdversarialValidationAgent.
- Robustness tests for Laplacian, mode count and edge dropout.
- Complete analytical multi-file workflow.
- v0.6 analytical web interface.


## 0.5.0

- Multi-file CSV and Excel upload.
- FileCatalogAgent.
- EntityResolutionAgent.
- TableLinkingAgent.
- TemporalAlignmentAgent.
- HeterogeneousGraphAgent.
- Cross-table join inference by normalized overlap.
- Deterministic entity normalization.
- Heterogeneous MultiGraph construction.
- Multi-file web workflow and downloadable report.


## 0.4.0

- Automatic domain inference.
- Entity and relationship detection from ordinary tables.
- Numeric signal and time-column detection.
- Automatic edge-table generation.
- ModelingAgent added to the local workflow.
- User review of inferred relations in the web interface.
- Automatic and manual modeling modes.


## 0.3.0

- Local Streamlit web application.
- CSV, XLSX and XLSM import.
- Excel sheet selection.
- Interactive graph-column mapping.
- Configurable spectral and intervention analysis.
- Local JSON report download.
- End-to-end workflow API and tests.


## 0.2.0

- Deterministic local multi-agent coordinator.
- Data quality, graph builder, root cause, simulation and validation agents.
- Complete audit trail.
- Domain profiles for fleet, mining, supply chain, cybersecurity, fraud, energy and telecom.
- Allow-listed local tool registry with write approval.
- Optional Ollama local-model client.
- Agentic fleet demo and tests.

## 0.1.0

- Initial graph dataset API.
- Spectral analysis and IPR.
- Hotspot localization.
- Node and edge ablation.
- Matched controls and empirical p-values.
- Corridor analysis.
- Multiscale graph operator.
- CLI fleet demonstration.

## 3.4.0
- Added optional PostgreSQL ledger backend and SQL migration asset.
- Added scoped RBAC roles and OIDC-ready trusted principal headers.
- Added per-collection tamper-evident SHA-256 hash chains.
- Added liveness, readiness, Prometheus metrics, and ledger integrity endpoints.
- Preserved shadow-first execution defaults and v3.2 API compatibility.

## 3.4.0
- Added governed dry-run sandbox bridge and `/v3/runtime/sandbox`.
- Added HS256 bearer JWT validation with issuer, audience, expiry and RBAC mapping.
- Added bounded trace recording and `/v3/traces` diagnostics.
- Added optional OpenTelemetry and auth dependency groups.
- Added PostgreSQL tenant/project RLS migration.
- Added v3.4 architecture notes, ADR and release notes.

## 3.7.0
- Added read-only GitHub repository, issue, and pull-request discovery.
- Added multi-model PhiGraph Code benchmark suites with cost and latency metadata.
- Added deterministic lint and type-check verifier profiles to the allow-list.
- Added automated JSON and Markdown benchmark reports.
- Added v3.7 API endpoints for benchmark suites and GitHub read-only retrieval.

## 3.8.0
- Commit snapshots, trace graphs, model adapters, isolated patch evaluation, and benchmark confidence intervals.

## 3.9.0

- Added reproducible JSONL benchmark corpora with content hashes.
- Added OpenAI-compatible provider adapter with measured latency, tokens, and configured cost.
- Added read-only GitHub commit archive acquisition with safe extraction.
- Added deterministic security scanning and dependency inventory.
- Added patch quality gates and repeated corpus experiments.
- Added scientific JSON/Markdown reports.
- Added v3.9 API endpoints for corpus validation, security scanning, dependency inventory, and patch quality.
- Verified 107 tests.

## 4.0.0

- Froze PhiGraph Protocol v2.0.0 public contract.
- Added stable `phigraph.protocol`, `phigraph.core`, `phigraph.code`, and `phigraph.sdk` namespaces.
- Added consolidated `PhiGraphSettings` environment configuration.
- Added provider-neutral Python SDK with scope and idempotency propagation.
- Separated Core, Code, and Cyber product boundaries while preserving v3 compatibility.
- Added release-candidate architecture, SDK, protocol, ADR, and compatibility tests.
