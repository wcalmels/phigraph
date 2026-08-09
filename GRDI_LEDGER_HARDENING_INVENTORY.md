# GRDI Ledger Hardening Inventory

**Branch:** `feature/grdi-foundation-1.0-rc`
**Base:** `main@06df1eb`
**Date:** 2026-08-08
**Scope:** documentation only — no functional changes in this phase

This inventory catalogs every ledger access pattern relevant to GRDI Foundation
1.0-RC. It is the input for ADR-020 and the transactional refactor.

## Search commands (baseline)

```text
rg -n "ledger\._lock|ledger\._read|ledger\._write|ledger\._rechain_payload" src tests
rg -n "register_scoped_record|register_scoped_record_once|update_scoped_record|repair_chain" src tests
```

## Summary matrix by collection

| Collection | Canonical key (today) | Idempotent op | Scoped uniqueness enforced | Multinode risk |
|---|---|---|---|---|
| `decision_envelopes` | `envelope_id` | no | append only; global dup check in `_append` | P0 duplicate / lost write |
| `authority_decisions` | `authority_decision_id` | no | append only; global dup check | P0 |
| `execution_requests` | `plan_id` | no | append only; global dup check | P0 |
| `gateway_decisions` | `plan_id` | append once (immutable) | in-process | P0 duplicate / forked chain |
| `gateway_decision_events` | `plan_id + ":SIMULATION_RECORDED"` | append-only transitions | none today | P0 missing event model |
| `shadow_execution_receipts` | `plan_id` | `register_scoped_record_once` | in-process scan by scope | P0 race → duplicate receipt |
| `shadow_outcomes` | `shadow_receipt_id` | `register_scoped_record_once` | in-process scan by scope | P0 race → duplicate outcome |
| `replay_reports` | `manifest_hash` | `register_scoped_record_once` | in-process scan by scope | P0 race → duplicate replay |
| `historical_comparisons` | `comparison_key` | `register_scoped_record_once` | in-process scan by scope | P0 race → duplicate comparison |

---

## Production code usages

### INV-001 — `GRDIService.register_envelope`

| Field | Value |
|---|---|
| File / function | `src/phigraph/grdi/service.py` → `register_envelope` |
| Collection | `decision_envelopes` |
| Operation | append |
| Uniqueness key | `envelope_id` |
| Scope | `tenant_id`, `project_id` from envelope |
| Current atomicity | `register_scoped_record` → `_append` under `EvidenceLedger._lock` |
| JSON | single-node RLock + full read/write |
| SQLite | backend RLock + `write_all` full snapshot replace |
| PostgreSQL | table lock + scoped DELETE/INSERT snapshot |
| Multiprocess/multinode risk | **P0** — two nodes can append same logical envelope if IDs collide; cross-tenant ID collision blocked incorrectly by global `_append` dup check |
| Proposed API | `append_scoped(collection, record, canonical_key="envelope_id", scope=...)` |
| Priority | **P0** |

### INV-002 — `GRDIService.authorize`

| Field | Value |
|---|---|
| File / function | `src/phigraph/grdi/service.py` → `authorize` |
| Collection | `authority_decisions` |
| Operation | append |
| Uniqueness key | `authority_decision_id` |
| Scope | tenant/project from caller |
| Current atomicity | `register_scoped_record` → `_append` |
| JSON / SQLite / PostgreSQL | same as INV-001 |
| Multiprocess/multinode risk | **P0** — concurrent authorize for same envelope not deduplicated |
| Proposed API | `append_scoped` (future: optional `append_scoped_once` keyed by `envelope_id` + policy version) |
| Priority | **P0** |

### INV-003 — `GRDIService.create_execution_plan` (request)

| Field | Value |
|---|---|
| File / function | `src/phigraph/grdi/service.py` → `create_execution_plan` |
| Collection | `execution_requests` |
| Operation | append |
| Uniqueness key | `plan_id` |
| Scope | tenant/project |
| Current atomicity | non-transactional pair of `register_scoped_record` calls (request + gateway) |
| Multiprocess/multinode risk | **P0** — partial plan creation if second append fails; no cross-collection transaction |
| Proposed API | `run_scoped_transaction([append_scoped(...), append_scoped(...)])` |
| Priority | **P0** |

### INV-004 — `GRDIService.create_execution_plan` (gateway)

| Field | Value |
|---|---|
| File / function | `src/phigraph/grdi/service.py` → `create_execution_plan` |
| Collection | `gateway_decisions` |
| Operation | append (initial immutable row) |
| Uniqueness key | **`plan_id`** (canonical); `gateway_decision_id` is record id only |
| Scope | tenant/project |
| Linked key | 1:1 with `execution_requests.plan_id` |
| Multiprocess/multinode risk | **P0** — orphan gateway or orphan request without cross-collection tx |
| Proposed API | `run_scoped_transaction`: append request + append gateway (`plan_id` key) |
| Priority | **P0** |

### INV-005 — `GRDIService.simulate_execution_plan`

| Field | Value |
|---|---|
| File / function | `src/phigraph/grdi/service.py` → `simulate_execution_plan` |
| Collections | `shadow_execution_receipts`, `gateway_decision_events` (target) |
| Operation | read-check-write + `register_scoped_record_once` + legacy `update_scoped_record` |
| Uniqueness key | `plan_id` (receipt); simulation event per plan |
| Scope | tenant/project |
| Current atomicity | outer `with self.core.ledger._lock` + in-place gateway mutation |
| Multiprocess/multinode risk | **P0** — duplicate receipts; forked chain without collection chain lock |
| Proposed API | tx with chain locks: once receipt + append `gateway_decision_events` |
| Priority | **P0** |

**Private ledger access:** `with self.core.ledger._lock` (line ~176)

**Legacy defect:** `update_scoped_record` on `gateway_decisions` — **removed in 1.0-RC**.

### INV-006 — `GRDIService.record_shadow_outcome`

| Field | Value |
|---|---|
| File / function | `src/phigraph/grdi/service.py` → `record_shadow_outcome` |
| Collection | `shadow_outcomes` |
| Operation | read-check-write + `register_scoped_record_once` |
| Uniqueness key | `shadow_receipt_id` |
| Scope | tenant/project |
| Current atomicity | `with self.core.ledger._lock`; checks existing by receipt via query + once-register |
| Multiprocess/multinode risk | **P0** — two outcomes per receipt |
| Proposed API | `append_scoped_once(..., canonical_key=receipt_id)` with DB unique constraint |
| Priority | **P0** |

**Private ledger access:** `with self.core.ledger._lock` (line ~264)

### INV-007 — `GRDIService.create_replay_report`

| Field | Value |
|---|---|
| File / function | `src/phigraph/grdi/service.py` → `create_replay_report` |
| Collection | `replay_reports` |
| Operation | build manifest + `register_scoped_record_once` |
| Uniqueness key | `manifest_hash` (snapshot identity excluding chain heads) |
| Scope | tenant/project |
| Current atomicity | `with self.core.ledger._lock` |
| Multiprocess/multinode risk | **P0** — duplicate replay reports for same manifest |
| Proposed API | `append_scoped_once(..., canonical_key=manifest_hash)` |
| Priority | **P0** |

**Private ledger access:** `with self.core.ledger._lock` (line ~377)

### INV-008 — `GRDIService.compare_replays`

| Field | Value |
|---|---|
| File / function | `src/phigraph/grdi/service.py` → `compare_replays` |
| Collection | `historical_comparisons` |
| Operation | compare signed reports + `register_scoped_record_once` |
| Uniqueness key | `comparison_key` = hash(baseline_replay_id, candidate_replay_id, policy_version) |
| Scope | tenant/project |
| Current atomicity | `with self.core.ledger._lock` |
| Multiprocess/multinode risk | **P0** — duplicate comparisons |
| Proposed API | `append_scoped_once(..., canonical_key=comparison_key)` |
| Priority | **P0** |

**Private ledger access:** `with self.core.ledger._lock` (line ~421)

### INV-009 — `GRDIService._persist_gateway_state` (legacy — to remove)

| Field | Value |
|---|---|
| File / function | `src/phigraph/grdi/service.py` → `_persist_gateway_state` |
| Collection | `gateway_decisions` (today) |
| Operation | **`update_scoped_record`** + global `_rechain_payload` |
| Multiprocess/multinode risk | **P0** — mutates immutable evidence; chain rechain cost |
| Proposed API | **`append_scoped` on `gateway_decision_events`** inside simulate transaction |
| Priority | **P0** (remove before 1.0-RC) |

### INV-010 — `ReplayEngine.build_report` / `validate_report_against_sources`

| Field | Value |
|---|---|
| File / function | `src/phigraph/grdi/replay.py` |
| Collections | all GRDI chain collections + `replay_reports` |
| Operation | read-only `verify_chain`, `query`, hash recompute |
| Current atomicity | no lock; reads full payload via `query`/`_read` indirectly |
| Multiprocess/multinode risk | **P1** — torn read during concurrent append; must not call `repair_chain` |
| Proposed API | `list_scoped`, `get_scoped`, `verify_chain()` public read-only |
| Priority | **P1** |

### INV-011 — GRDI read paths (`ledger.query` + Python filter)

| Field | Value |
|---|---|
| Files | `src/phigraph/grdi/service.py`, `src/phigraph/grdi/replay.py` |
| Functions | `_get_execution_request`, `_get_gateway_decision`, `_get_shadow_receipt`, `_get_shadow_outcome*`, `_get_replay_row`, `_find_row`, `_list_prior_reports` |
| Operation | O(n) scan per call (`limit=100000`) |
| Multiprocess/multinode risk | **P2** performance + stale read |
| Proposed API | `get_scoped(collection, canonical_key, scope)` with indexed lookup |
| Priority | **P1** (correctness via snapshot reads), **P2** (performance) |

### INV-012 — `EvidenceLedger.register_scoped_record` (implementation)

| Field | Value |
|---|---|
| File / function | `src/phigraph/core_v3/ledger.py` → `register_scoped_record` |
| Operation | `_append` |
| Issue | duplicate check is **global per collection**, not scoped by tenant/project |
| Multiprocess/multinode risk | **P0** false duplicate errors cross-scope; no true scoped uniqueness |
| Proposed API | replace with `append_scoped` enforcing `(tenant, project, collection, canonical_key)` |
| Priority | **P0** |

### INV-013 — `EvidenceLedger.register_scoped_record_once` (implementation)

| Field | Value |
|---|---|
| File / function | `src/phigraph/core_v3/ledger.py` → `register_scoped_record_once` |
| Operation | read full payload → linear scan → append → write |
| Scoped check | yes (tenant/project + unique_key field) |
| JSON / SQLite | `_lock` serializes single node |
| PostgreSQL | `_lock` is process-local; DB has no unique on canonical business keys |
| Multiprocess/multinode risk | **P0** |
| Proposed API | `append_scoped_once` backed by UNIQUE constraint + advisory lock |
| Priority | **P0** |

### INV-014 — `EvidenceLedger.update_scoped_record` (legacy)

| Field | Value |
|---|---|
| File / function | `src/phigraph/core_v3/ledger.py` → `update_scoped_record` |
| Operation | in-place mutation + `_rechain_payload` entire ledger |
| GRDI 1.0-RC | **prohibited** on GRDI paths; gateway uses append-only events |
| Proposed API | not exposed to GRDI; Core mutable rows only if ever required |
| Priority | **P0** removal from GRDI |

### INV-015 — `EvidenceLedger.repair_chain`

| Field | Value |
|---|---|
| File / function | `src/phigraph/core_v3/ledger.py`, `src/phigraph/migration.py` |
| Operation | `_rechain_payload` + `_write`; exposed via migration helper |
| GRDI usage | **must not** be called from replay/read paths (ADR-019) |
| Proposed API | admin-only `repair_chain()` outside GRDI hot path; never auto on read |
| Priority | **P1** governance |

### INV-016 — Backend direct access

| Field | Value |
|---|---|
| Files | `src/phigraph/core_v3/ledger.py` → `_read`/`_write` → `backend.read_all`/`write_all` |
| Backends | `JsonLedgerBackend`, `SQLiteLedgerBackend`, `PostgreSQLLedgerBackend` |
| Pattern | full snapshot read/modify/write |
| PostgreSQL | `LOCK TABLE ... EXCLUSIVE`, scoped DELETE + bulk INSERT |
| Multiprocess/multinode risk | **P0** — not row-level transactional for idempotent keys |
| Proposed API | row-level operations inside `run_scoped_transaction` |
| Priority | **P0** |

### INV-017 — API idempotency layer

| Field | Value |
|---|---|
| File | `src/phigraph/core_v3/auth_deps.py`, `src/phigraph/grdi/api.py` |
| Operation | HTTP `Idempotency-Key` dedupes **HTTP responses** |
| Canonical key | separate layer — identifies persisted entity |
| Risk | **P1** if conflated with ledger keys |
| Resolution | keep layers separate per ADR-020 §10 |
| Priority | **P1** documentation + tests |

### INV-018 — Chain head fork without collection lock

| Field | Value |
|---|---|
| Location | `register_scoped_record_once`, `_append` in `ledger.py` |
| Issue | concurrent appends with different canonical keys read same `chain_prev` |
| Multiprocess/multinode risk | **P0** — bifurcated `_chain` |
| Proposed API | chain `LockRef` before every append (ADR-020 §4) |
| Priority | **P0** |

---

## Test-only private ledger access (documented, not fixed in this phase)

| ID | File | Purpose |
|---|---|---|
| T-001 | `tests/test_grdi_outcome_ledger.py` → `_mutate_ledger_row` | adversarial tampering via `_lock`/`_read`/`_write`/`_rechain_payload` |
| T-002 | `tests/test_grdi_replay_audit.py` | break chain hash without rechain |
| T-003 | `tests/test_grdi_execution_gateway.py` | direct `update_scoped_record` |

These remain acceptable in tests until contract tests provide sanctioned mutation helpers.

---

## Canonical keys and idempotency map

| Business invariant | Canonical key field | Idempotency mechanism today | Target constraint |
|---|---|---|---|
| one gateway per plan | `plan_id` | append once (no idempotency today) | UNIQUE(scope, gateway_decisions, plan_id) |
| simulation recorded | `plan_id + ":SIMULATION_RECORDED"` | none (in-place update today) | `append_scoped_once` on `gateway_decision_events` |
| one receipt per plan | `plan_id` | `register_scoped_record_once` | UNIQUE(scope, collection, plan_id) |
| one outcome per receipt | `shadow_receipt_id` | `register_scoped_record_once` | UNIQUE(scope, collection, shadow_receipt_id) |
| one replay per manifest | `manifest_hash` | `register_scoped_record_once` | UNIQUE(scope, collection, manifest_hash) |
| one comparison per pair | `comparison_key` | `register_scoped_record_once` | UNIQUE(scope, collection, comparison_key) |
| HTTP replay create | `Idempotency-Key` + payload | Core HTTP cache | ledger `manifest_hash` via `append_scoped_once` |

---

## Resolved decisions (ADR-020 review 2026-08-08)

| Topic | Resolution |
|---|---|
| `_append` global dup check | Legacy defect; scoped uniqueness in new API |
| Cross-collection tx | Required: plan+gateway, receipt+gateway-event |
| Gateway mutation | Append-only events; no `update_scoped_record` in GRDI |
| Gateway canonical key | **`plan_id`** (not `gateway_decision_id`) |
| Chain serialization | Collection chain lock before `chain_prev` |
| PostgreSQL PK | `(tenant, project, collection, canonical_key)` + scoped `record_id` |
| HTTP idempotency | Separate from canonical entity key |
| Corrupt replay baselines | Catch ValueError, KeyError, TypeError; skip invalid |
| Key rotation | Verify with keyring; never re-sign historical records |
| JSON/SQLite CAS | Serialize; loser gets VersionConflict |
| Backend concurrency | JSON single-process; SQLite single-node multiprocess; PG multinode |
| **Core public transactional API** | **IMPLEMENTED** (4.1.0-rc.6): `append_scoped*`, `get/list_scoped`, CAS, `run_scoped_transaction` on JSON/SQLite |
| **GRDI service migration** | **OPEN** — still uses `_lock` and legacy scoped methods |

---

## Backend guarantee matrix (1.0-RC)

| Backend | Concurrency | Guarantee |
|---|---|---|
| JSON | single-process only | Process-wide lock; ACID within one process |
| JSON | multiprocess | `TransactionUnavailable` — no cross-process lock |
| SQLite | single-node multiprocess | Scoped table + `BEGIN IMMEDIATE`; real SQLite transactions |
| PostgreSQL | multi-node | Row UNIQUE + advisory locks + `phigraph_chain_heads` sequence |

---

## Priority rollup

| Priority | Count | Theme |
|---|---|---|
| **P0** | 14 | chain lock, gateway events, idempotent once, cross-collection tx |
| **P1** | 5 | torn reads, HTTP idempotency docs, repair governance |
| **P2** | 1 | query scan performance |
