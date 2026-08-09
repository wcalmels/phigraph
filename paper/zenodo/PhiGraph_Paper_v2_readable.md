---
abstract: |
  Software agents and artificial-intelligence systems can produce
  claims, recommendations, and action proposals faster than
  organizations can verify and govern them. This paper presents PhiGraph
  Core 4.1.0-rc.6, an MIT-licensed, model-agnostic system that treats
  model output as a proposal rather than as verified truth. PhiGraph
  represents claims, evidence, verifications, action proposals, policy
  decisions, and outcomes as linked records; stores them in a
  scope-tagged, tamper-evident ledger; and places policy evaluation
  between agent proposals and operational execution. Core 4.1 adds a
  scoped transactional ledger with declared write locks, append-only
  GRDI hash chains, mutable Core compare-and-set collections, and
  fail-closed `verify_scoped_chain` for JSON and SQLite backends.
  Governed Relational Decision Intelligence (GRDI) 0.4.0 extends the
  stack with a persisted shadow decision chain---from decision envelopes
  and authority through simulated gateway receipts, outcomes, and
  deterministic replay audit---without external execution in the current
  release. We additionally describe PhiGraph HAV v0.2, a fail-closed
  verification layer that checks agent-generated text against an
  explicitly supplied authoritative state. Replay and shadow modes
  cannot execute external actions, while higher-authority modes require
  both an explicit executor and an allowing policy decision. Engineering
  verification comprises 319 automated tests on `main@a5a7187` (262
  baseline, 57 scoped transactional contract, and 11 HAV-specific
  tests), including scoped-integrity, idempotent append-once, and GRDI
  replay-audit cases; continuous integration targets Python 3.10--3.13.
  An initial external experiment on the CIC-IDS2017 Friday DDoS flow
  file compares a PhiGraph relational score with three unsupervised
  baselines. Local Outlier Factor is strongest on this tabular
  benchmark; PhiGraph ranks second by PR-AUC and attains 0.840 precision
  at a 10% alert budget. The experiment demonstrates functional
  integration, not state-of-the-art superiority. PhiGraph is therefore
  presented as an auditable governance substrate and research prototype
  (development candidate), not as a proof of correctness, causal
  identification, or safe autonomous operation.
author:
- |
  Walter Calmels von Dem Knesebeck\
  TUCH Systems, Santiago, Chile\
  <wcalmels@phi47.cl>
bibliography: paper/references.bib
date: August 2026 (v2 draft)
title: |
  **PhiGraph Core 4.1: A Shadow-First Evidence Ledger,\
  Transactional Scoped Storage, and GRDI for Software-Agent Operations**
---

**Keywords:** AI governance; software agents; provenance; evidence
ledger; transactional ledger; GRDI; replay audit; graph intelligence;
policy enforcement; shadow deployment; claim verification; reproducible
software

# Introduction

Modern software agents can synthesize text, modify code, recommend
operational changes, invoke tools, and coordinate multi-step workflows.
Their outputs may be useful without being reliable, authorized, or
supported by reproducible evidence. This creates a control problem: an
organization must determine what was claimed, which evidence supported
or refuted it, which policy governed a proposed action, who approved it,
and what happened after evaluation or execution.

Existing guidance emphasizes lifecycle risk management and traceability.
The NIST AI Risk Management Framework organizes activities around
governing, mapping, measuring, and managing AI risk (Tabassi 2023). W3C
PROV provides a general vocabulary for provenance (Lebo et al. 2013),
while model cards and dataset datasheets improve documentation of
released artifacts (Mitchell et al. 2019; Gebru et al. 2021). These
approaches are important, but they do not by themselves define an
operational boundary between a model-generated proposal and an
authorized action.

PhiGraph addresses this boundary through an evidence-oriented protocol
and a policy-gated runtime. Its central invariant is that model output
is a candidate claim or action proposal, not verified truth or implicit
authority. The system records relationships among claims, evidence,
verification results, policies, approvals, and outcomes so that a
decision can be reconstructed after the fact.

This paper makes seven contributions:

1.  a typed protocol for claims, evidence, verifications, action
    proposals, policy decisions, and outcomes;

2.  a runtime in which policy evaluation and an explicit executor are
    necessary conditions for external action;

3.  a backend-neutral, scope-tagged ledger with hash-chain integrity
    metadata and optional HMAC evidence signatures;

4.  a scoped transactional store (Core 4.1) with declared write locks,
    idempotent append-once semantics, and fail-closed chain verification
    on JSON and SQLite backends;

5.  HAV v0.2, a fail-closed extension that verifies agent-generated
    textual claims against an authoritative external state and records
    the result through the same protocol and ledger;

6.  GRDI 0.4.0, a persisted shadow decision chain from HAV-linked
    envelopes through authority, simulated gateway receipts, outcomes,
    and replay audit, without external execution in the current release;
    and

7.  a bounded empirical evaluation comprising software verification and
    an external anomaly-ranking experiment, together with explicit
    threats to validity.

# Related Work

## Governance, documentation, and provenance

The NIST AI RMF is a voluntary, use-case-agnostic framework for managing
AI risk (Tabassi 2023). PhiGraph is not an implementation or
certification of that framework; it provides operational records that
may support governance activities. PROV-O formalizes entities,
activities, agents, and provenance relations (Lebo et al. 2013).
PhiGraph uses a narrower application protocol centered on verification
and policy-gated action. A future interoperability layer could map
PhiGraph records to PROV-O.

Model cards (Mitchell et al. 2019) and datasheets for datasets (Gebru et
al. 2021) make intended uses, evaluation conditions, and limitations
explicit. PhiGraph applies a related transparency principle at runtime:
each claim and action remains linked to its evidence, decision, and
outcome rather than relying only on static release documentation.

## Relational representations and software assurance

Graph-based representations make entities and relationships first-class
and support structured reasoning ([Battaglia et al.]{.nocase} 2018).
PhiGraph uses heterogeneous graphs and classical graph analytics; it
does not require a graph neural network and does not claim that graph
structure alone establishes causality. In software assurance, in-toto
protects software-supply-chain integrity through verifiable step
metadata (Torres-Arias et al. 2019). PhiGraph shares an emphasis on
attributable records but targets a broader
claim--evidence--policy--action lifecycle.

Agentic systems introduce risks including tool misuse, privilege
compromise, untraceable actions, and cascading errors. The OWASP Agentic
Security Initiative provides an industry threat taxonomy (OWASP Agentic
Security Initiative 2025). PhiGraph's deny-by-default policy, approval
requirements, idempotency controls, and shadow-first deployment are
engineering controls relevant to these risks; they are not a complete
security solution.

## Automated claim verification

Large language models can generate fluent text that is not supported by,
or directly contradicts, available evidence, a phenomenon surveyed
broadly across natural-language-generation tasks (Ji et al. 2023). FEVER
established claim verification against textual evidence as a distinct
research problem, using retrieval and entailment models over a large
Wikipedia-derived claim set (Thorne et al. 2018). PhiGraph's HAV
extension (Section [4.5](#sec:hav){reference-type="ref"
reference="sec:hav"}) targets a narrower, operational instance of this
problem: claims that an AI agent makes about the status of a software
system, checked against a caller-supplied authoritative state rather
than an open-domain knowledge base. It does not use a trained entailment
model and does not claim comparable coverage or accuracy to FEVER-style
systems; its contribution is a fail-closed policy binding between
extracted claims and PhiGraph's existing evidence ledger and governance
protocol.

# System Model and Design Goals {#sec:systemmodel}

Let an agent produce a proposal $$P = (C, A),$$ where $C$ is a set of
claims and $A$ is a set of proposed actions. A claim does not become
verified merely because an agent assigns it high confidence. Instead, a
verifier records a result over a claim and an explicit evidence set.
Similarly, an action is not authorized by its presence in $P$: the
policy engine evaluates the action under a runtime mode and an approval
set.

PhiGraph is designed around six goals:

1.  **Evidence boundedness:** when evidence identifiers are supplied,
    verification results reference evidence already registered in the
    ledger.

2.  **Least authority:** absence of a matching policy blocks an action.

3.  **Traceability:** claims, decisions, and outcomes remain
    reconstructable.

4.  **Safe evaluation:** replay and shadow runs never execute an
    external action.

5.  **Scope tagging:** tenant and project identifiers propagate through
    stored records and can be used to filter queries.

6.  **Model neutrality:** deterministic programs, statistical models,
    and language-model agents can use the same protocol.

# PhiGraph Architecture {#sec:architecture}

<figure id="fig:architecture" data-latex-placement="H">

<figcaption>PhiGraph separates agent proposals from verification, policy
evaluation, and execution. Core 4.1 persists scope-tagged records
through a transactional store; HAV verifies candidate text against
supplied state; GRDI appends a shadow decision chain through the same
store. Arrows indicate recorded processing relationships, not automatic
trust propagation.</figcaption>
</figure>

## Canonical protocol

Protocol version 2.0.0 exposes six principal frozen dataclass record
schemas:

- `Claim`: statement, type, subject, issuer, status, confidence,
  evidence references, and optional supersession;

- `Evidence`: kind, source, payload, status, content hash, observation
  time, and metadata;

- `Verification`: claim, verifier, method, result, evidence references,
  rationale, and time;

- `ActionProposal`: action type, target, proposer, parameters, rationale
  claims, reversibility, and risk level;

- `PolicyDecision`: effect, applicable policies, reasons, required
  approvals, and time; and

- `Outcome`: action, status, whether execution occurred, observed
  effects, evidence references, and time.

Claim states distinguish proposed, unverified, partially verified,
verified, refuted, and superseded records. Policy effects distinguish
allow, warn, require approval, and block. These states make uncertainty
and governance decisions explicit instead of collapsing them into a
single confidence score. The current implementation does not require a
non-empty evidence set for every verified claim and does not assess
evidentiary sufficiency. This is an enforcement gap, not a guarantee
supplied by the protocol. In Core 4.1, each record type maps to a
tenant- and project-scoped collection: protocol records use mutable
scoped rows, while GRDI stages use chain-linked append-only collections
(Section [4.3](#sec:transactional-ledger){reference-type="ref"
reference="sec:transactional-ledger"}). Figure
[2](#fig:protocol-lifecycle){reference-type="ref"
reference="fig:protocol-lifecycle"} shows how the six record types
reference one another across a full claim-to-outcome cycle.

<figure id="fig:protocol-lifecycle" data-latex-placement="H">

<figcaption>The protocol’s recorded lifecycle. Solid arrows show
synchronous references (a verification cites claims and evidence; an
action proposal cites rationale claims; a policy decision governs a
proposal; an outcome follows a decision). Dashed arrows show
asynchronous feedback: a verification updates claim status, and an
outcome’s observed effects may be registered as new evidence for future
claims. Under Core 4.1, each record type is persisted in a scope-tagged
collection. The cycle is auditable, not automatic – each edge
corresponds to an explicit recorded reference, not an implicit trust
relationship.</figcaption>
</figure>

## Evidence ledger

The ledger supports JSON, SQLite, and PostgreSQL backends through a
common interface. Collections are maintained for claims, evidence,
verifications, actions, policy decisions, and outcomes. Most records are
appended. Claim verification performs a controlled in-place state
transition and then rebuilds the affected collection chains. Each
ordinary append computes $$h_i =
\operatorname{SHA256}\!\left(h_{i-1}\,\Vert\,k\,\Vert\,
\operatorname{canonical}(r_i)\right),$$ where $r_i$ is a record and $k$
identifies its collection. Verification checks link continuity and
recomputes each hash. Evidence payloads receive a SHA-256 content hash
and may be signed with HMAC-SHA256 when a signing key is supplied.

Chain verification detects changes relative to the currently stored
chain. This mechanism is *tamper evident*, not tamper proof: without an
external anchor or protected signing key, it cannot distinguish
malicious tampering from an authorized rebuild. An attacker with write
access to both the records and all integrity keys can rebuild a
consistent chain. Stronger deployment requires external key management,
append-only storage, access control, backups, and independent audit
anchors.

## Transactional scoped ledger {#sec:transactional-ledger}

Core 4.1.0-rc.6 adds a *scoped transactional* persistence layer for
multi-tenant deployments. Business records are keyed by tenant, project,
collection, and canonical business key, and stored with an explicit
payload hash, chain metadata, and row version. Public scoped operations
include `append_scoped`, `append_scoped_once`, `get_scoped`,
`list_scoped`, `compare_and_set_scoped`, and `run_scoped_transaction`;
integrity verification uses `verify_scoped_chain`, which recomputes
hashes, chain continuity, and chain-head consistency without repairing
data.

#### Write locks.

Every mutating call inside a transaction must declare its locks up
front. A *chain lock* covers an entire scoped collection and is required
before appending to chain-linked GRDI collections; a *canonical lock*
covers one business key within a collection. If a write touches a key
without the matching declared lock, the engine raises
`UndeclaredLockRef` rather than proceeding. Lock references are sorted
in a global order (tenant, project, collection, kind, key) before
acquisition to reduce deadlock risk across concurrent workers.

#### Atomic transactions.

`run_scoped_transaction` accepts a callback that performs multiple
scoped operations under one commit boundary. On the JSON backend, writes
are staged in thread-local state and flushed on success. JSON rejects
multiprocess transactional mode fail-closed because cross-process file
locking is not provided. On SQLite, the engine uses `BEGIN IMMEDIATE`
with scoped tables `phigraph_scoped_ledger` and `phigraph_chain_heads`.
A callback failure or commit error rolls back staged state and clears
transaction context.

#### Integrity verification.

`verify_scoped_chain` groups rows by scope and collection, validates
that internal columns match each record's `_chain` metadata, checks
payload hashes, detects missing or orphan chain heads, and rejects
sequence gaps. The check is *fail-closed*: any tamper or inconsistency
raises `LedgerIntegrityError`. This behavior is *implemented* for JSON
and SQLite in the current release; a PostgreSQL backend with the same
semantics is *specified* but not yet shipped.

Figure [3](#fig:scoped-transaction){reference-type="ref"
reference="fig:scoped-transaction"} summarizes the transaction boundary
and lock declaration requirement.

<figure id="fig:scoped-transaction" data-latex-placement="H">

<figcaption>Scoped transactional writes require pre-declared locks and
commit atomically on JSON (single-process) or SQLite
(<code>BEGIN IMMEDIATE</code>). Integrity verification is a separate
fail-closed read path.</figcaption>
</figure>

#### Chain-linked versus mutable collections.

GRDI persistence collections are *chain-linked*: each append extends a
per-scope hash chain and `compare_and_set_scoped` is rejected. Core
protocol collections (`claims`, `evidence`, `verifications`, `actions`,
`policy_decisions`, `outcomes`) are stored as *mutable* scoped rows with
standalone content hashes and support conditional updates. Mixing the
two modes in one transaction is permitted, but a compare-and-set on a
chain-linked collection always fails closed.
Figure [4](#fig:chain-mutable){reference-type="ref"
reference="fig:chain-mutable"} contrasts the two storage semantics.

<figure id="fig:chain-mutable" data-latex-placement="H">

<figcaption>Chain-linked GRDI collections extend an append-only scoped
hash chain; mutable Core collections support conditional updates without
chain linking.</figcaption>
</figure>

Figure [5](#fig:verify-scoped-chain){reference-type="ref"
reference="fig:verify-scoped-chain"} summarizes the fail-closed read
path.

<figure id="fig:verify-scoped-chain" data-latex-placement="H">

<figcaption><code>verify_scoped_chain</code> recomputes hashes and chain
metadata, checks head pointers and sequence continuity, and raises
<code>LedgerIntegrityError</code> on any inconsistency.</figcaption>
</figure>

## Policy-gated runtime

The policy engine matches action type, permitted runtime modes, maximum
risk, reversibility, and required approvals. No matching rule produces
an implicit deny decision. For an action $a$, decision $d$, mode $m$,
and executor $x$, the core execution condition is
$$\operatorname{execute}(a) \iff
\bigl(d.\mathrm{effect}=\mathrm{allow}\bigr)
\land \bigl(m\in\{\mathrm{copilot},\mathrm{guarded\_auto}\}\bigr)
\land (x\neq\varnothing).$$ Replay and shadow modes therefore generate
simulated outcomes with `executed=false`. The packaged deployment
configuration is stricter: it defaults to shadow-only operation, rejects
attempts to disable that boundary, and disables real connectors. The
core abstractions expose higher-authority modes for controlled future
integration, but the supplied deployment does not grant arbitrary
external execution.

## Human-Assisted Verification (HAV v0.2) {#sec:hav}

HAV v0.2 is an additive module (`phigraph.hav`) that checks candidate
textual output from an AI agent, such as a status summary or a release
note, against an authoritative state supplied explicitly by the caller,
and records the outcome through the existing Core protocol and ledger
described in Section [4](#sec:architecture){reference-type="ref"
reference="sec:architecture"}. HAV does not modify the ledger, policy
engine, or runtime described above; it is a client of that protocol.

#### Pipeline.

A verification request carries a candidate output string and an
`AuthoritativeState`: a set of source-attributed evidence facts, or an
explicit *unavailable* marker with a reason. A hybrid extractor combines
fixed regular-expression patterns for structured, repository-style
predicates (for example, test counts, CI or CodeQL status, and global
success or production-readiness phrasing) with a second extractor that
flags generic factual-looking substrings (percentages, dates,
quantities, and source attributions) without asserting their truth.
Every claim produced by the second extractor is marked
`requires_external_grounding=true` and is not treated as verified
evidence on its own. A verifier then compares each claim against the
authoritative state by subject and predicate, and classifies it as
supported, contradicted, unsupported, partially supported, or having
insufficient evidence.
Figure [6](#fig:hav-pipeline){reference-type="ref"
reference="fig:hav-pipeline"} traces this pipeline from candidate output
to ledger records.

<figure id="fig:hav-pipeline" data-latex-placement="H">

<figcaption>HAV v0.2 verification pipeline. The authoritative state is
supplied by the caller, not retrieved by HAV, and merges into the
verifier stage; an unavailable state is itself a valid input that the
fail-closed policy (Figure <a href="#fig:hav-flow"
data-reference-type="ref" data-reference="fig:hav-flow">7</a>) maps to a
blocking verdict.</figcaption>
</figure>

#### Fail-closed policy.

A dedicated policy, `PHIGRAPH_HAV_FAIL_CLOSED_V1`, converts claim
evaluations into one of five verdicts:

$$V(s, E) =
\begin{cases}
\textsc{source\_unavailable} & \text{if the authoritative state } s \text{ is unavailable} \\
\textsc{reject} & \text{if a critical claim in } E \text{ is contradicted} \\
\textsc{human\_review} & \text{if a critical claim in } E \text{ lacks sufficient evidence} \\
\textsc{warn} & \text{if any non-critical claim in } E \text{ is not supported} \\
\textsc{pass} & \text{otherwise,}
\end{cases}$$

evaluated in the listed order, where $E$ is the set of claim evaluations
for a request. Figure [7](#fig:hav-flow){reference-type="ref"
reference="fig:hav-flow"} renders this evaluation order as a decision
flowchart. Verdicts map onto the existing PhiGraph policy-decision
effects of Section [4](#sec:architecture){reference-type="ref"
reference="sec:architecture"} as shown in
Table [1](#tab:hav-mapping){reference-type="ref"
reference="tab:hav-mapping"}; in particular, an unavailable
authoritative source blocks the action rather than defaulting to a
permissive outcome.

<figure id="fig:hav-flow" data-latex-placement="H">

<figcaption>Decision flowchart for the fail-closed policy <span
class="math inline"><em>V</em>(<em>s</em>, <em>E</em>)</span>. Branches
are evaluated top to bottom; the first matching condition determines the
verdict, so an unavailable source always blocks regardless of claim
content, and a fully supported claim set only reaches <span
class="smallcaps">pass</span> after every stricter condition
fails.</figcaption>
</figure>

::: {#tab:hav-mapping}
  HAV verdict                        Core policy effect
  ---------------------------------- --------------------
  [pass]{.smallcaps}                 `allow`
  [warn]{.smallcaps}                 `warn`
  [reject]{.smallcaps}               `block`
  [human_review]{.smallcaps}         `require_approval`
  [source_unavailable]{.smallcaps}   `block`

  : Mapping from HAV verdicts to PhiGraph Core policy effects.
:::

#### Ledger integration and receipts.

For each request, HAV registers the supplied evidence facts as
`Evidence` records, registers each extracted claim as a `Claim` record,
records a `Verification` per claim, registers an `ActionProposal`
representing acceptance of the candidate output, and records a
`PolicyDecision` carrying the mapped effect. A `HAVReceipt` bundling the
verdict, claim evaluations, and a SHA-256 hash of the candidate output
is itself stored as ledger evidence and, when a receipt-signing key is
configured, signed with the same HMAC-SHA256 mechanism used elsewhere in
Core. Tenant and project identifiers supplied with the request propagate
to every record, consistent with the scope-tagging goal in
Section [3](#sec:systemmodel){reference-type="ref"
reference="sec:systemmodel"}.

#### Security posture.

HAV never executes candidate output or any generated code; it only
pattern-matches and compares strings. It does not persist a database
file, and the packaged module contains no embedded credentials. The HTTP
endpoints (`/v3/hav/verify`, `/v3/hav/factual/extract`,
`/v3/hav/consistency`) accept an optional `PHIGRAPH_HAV_API_KEY`; when
set, requests must present a matching `X-API-Key` header, compared using
constant-time comparison, and are otherwise rejected. Multi-output
consistency checking (shared-token overlap and conflicting status terms
across several candidate outputs) is exposed only as an auxiliary
diagnostic signal, not as a verification result on its own, and does not
influence the policy decision above.

## GRDI shadow decision chain {#sec:grdi}

Governed Relational Decision Intelligence (GRDI) version 0.4.0 extends
PhiGraph with a persisted *shadow* decision chain that binds HAV
verification, human or policy authority, execution planning, simulated
gateway decisions, shadow receipts, outcomes, and deterministic replay
audit. GRDI writes only through the scoped transactional API in
Section [4.3](#sec:transactional-ledger){reference-type="ref"
reference="sec:transactional-ledger"} and never invokes external
connectors or live executors in the current release.

#### State separation.

Verification uses `VERIFIED` or `NOT_VERIFIED`; authorization uses
`AUTHORIZED`, `NOT_AUTHORIZED`, or `REQUIRES_APPROVAL`; execution
remains `NOT_EXECUTED` throughout Foundation and shadow increments.
These states are stored as distinct fields. A passing HAV receipt does
not by itself authorize an action; an authorized envelope does not imply
that an external action was executed. The shadow execution gateway may
record `SIMULATED` plans and signed receipts while preserving
`execution_state=NOT_EXECUTED`.

#### Persisted chain.

A typical shadow path appends, in order: a `DecisionEnvelope` (HAV
receipt and proposed action), an `AuthorityDecision`, an
`ExecutionRequest`, a `GatewayDecision`, an optional
`GatewayDecisionEvent`, a `ShadowExecutionReceipt`, and a
`ShadowOutcomeRecord`. Replay audit appends `ReplayReport` and
`HistoricalComparison` records that re-verify the stored chain without
re-running simulation or authority evaluation. Invalid signatures, scope
mismatches, or broken links fail closed into explicit `INVALID` or
`INCOMPLETE` replay states; replay never calls chain repair routines.

Figure [8](#fig:grdi-pipeline){reference-type="ref"
reference="fig:grdi-pipeline"} shows the end-to-end shadow flow
implemented on `main` at Core 4.1.0-rc.6. External execution and
PostgreSQL-scoped transactions remain *specified* future work, not
claims of this paper.

<figure id="fig:grdi-pipeline" data-latex-placement="H">

<figcaption>GRDI 0.4.0 shadow decision chain. Each box is an
append-only, scope-tagged ledger collection linked through the
transactional store. Replay audit reads and verifies history without
invoking connectors or re-running simulation.</figcaption>
</figure>

## API, SDK, and operations {#sec:api}

The Python SDK can send tenant and project headers, API-key or bearer
credentials, and idempotency keys. Authentication, PostgreSQL
persistence, and signing are supported by lower-level Core components
when explicitly configured. The packaged application does not currently
wire every one of these options into the Core v3 router. Its Docker
configuration must therefore be treated as a local evaluation setup
unless protected by an external authentication and network boundary.
Scope headers are application metadata and query filters; the present
implementation does not provide end-to-end tenant isolation or
same-scope referential-integrity guarantees. HAV and GRDI HTTP surfaces
inherit the same deployment boundary: optional API keys on HAV routes,
shadow-default runtime configuration, and no live connector execution in
the packaged stack.

# Evaluation

## Research questions

The evaluation addresses five bounded questions:

::: description
Is the software version mechanically testable across its supported
Python versions and packaging paths?

Do the scoped transactional backends enforce declared write locks,
idempotent append-once semantics, and fail-closed `verify_scoped_chain`
behavior on JSON and SQLite?

Does GRDI replay audit deterministically verify persisted shadow chains
without re-simulation or external connector invocation?

Does the HAV fail-closed policy produce the intended blocking or passing
behavior on hand-constructed scenarios covering a contradicted critical
claim, an unavailable authoritative source, and a supported numeric
claim?

Does the current relational anomaly score produce useful rankings on one
external network-flow benchmark relative to simple unsupervised
baselines?
:::

It does not test whether PhiGraph prevents all unsafe agent actions,
proves causality, outperforms specialized state-of-the-art
intrusion-detection systems, measures HAV's claim-extraction accuracy
against a labeled claim corpus, or establishes Byzantine fault tolerance
for scoped storage.

## Software verification

To address RQ1, the software tree contains 319 automated tests at commit
`a5a7187` on `main`: 262 baseline tests covering protocol records,
legacy and scoped ledger paths, policy evaluation, runtime modes,
persistence backends, API and SDK boundaries, agent workflows, graph
operations, benchmarks, and deployment configuration, plus 57 scoped
transactional contract tests and 11 HAV-specific tests covering claim
extraction, connectors, the fail-closed policy, the API surface, and
API-key enforcement. Continuous integration is configured to install the
declared extras and run the suite on Python 3.10, 3.11, 3.12, and 3.13;
separate jobs build the Python distribution, install its wheel in an
isolated environment, and build the Docker image. A local run on August
9, 2026 executed all 319 tests successfully. A separate synthetic
benchmark attempt under local Python 3.14, which is outside the CI
matrix, stopped with an ARPACK eigensolver error and is excluded from
the reported empirical results. Passing tests establish conformance to
encoded cases, not correctness for all deployments.

## HAV verification scenarios {#sec:hav-scenarios}

To address RQ4, we exercised the running HAV API with three scenarios
chosen to cover the fail-closed policy's distinguishing branches, in
addition to the 11 automated unit and integration tests. In the first,
the candidate output asserts that all checks passed and the repository
is production-ready while the supplied authoritative state marks CodeQL
as failed and the release gate as blocked; the policy returned
[reject]{.smallcaps}, mapped to a `block` policy decision recorded in
the ledger. In the second, the authoritative source was marked
unavailable; the policy returned [source_unavailable]{.smallcaps}, also
mapped to `block`, rather than defaulting to a permissive outcome. In
the third, the candidate output correctly reports a numeric test count
that matches the supplied evidence; the policy returned
[pass]{.smallcaps}. All three outcomes matched the behavior implied by
the policy definition in Section [4.5](#sec:hav){reference-type="ref"
reference="sec:hav"}. This is a confirmation of implemented decision
logic on hand-constructed inputs, not a statistical evaluation of
extraction accuracy, adversarial robustness, or coverage over naturally
occurring agent output; the pattern-based extractor is not expected to
generalize beyond the repository-status vocabulary encoded in its rules.

## Transactional ledger integrity {#sec:txn-eval}

To address RQ2, the repository includes 57 contract tests (JSON and
SQLite) covering idempotent append-once under concurrency,
undeclared-lock rejection, thread-local JSON transaction isolation,
compare-and-set on mutable Core collections without breaking append-only
GRDI chains, commit-failure cleanup, and adversarial
`verify_scoped_chain` cases (missing heads, orphan heads, sequence gaps,
column tampering, and coordinated metadata manipulation; see
Figure [5](#fig:verify-scoped-chain){reference-type="ref"
reference="fig:verify-scoped-chain"}). These tests establish
*implemented* integrity behavior for the shipped backends; they do not
prove security against a privileged attacker with signing keys and
unrestricted storage access.

## GRDI replay audit scenarios {#sec:grdi-eval}

To address RQ3, GRDI replay and historical-comparison modules are
covered by automated tests that rebuild manifest hashes from persisted
shadow records, reject tampered receipt links, and assert explicit
non-execution invariants (`replay_executed=false`,
`connector_invoked=false`). These tests confirm *implemented* read-only
audit behavior on JSON and SQLite backends; they do not establish causal
correctness of shadow simulations or semantic equivalence between
production deployments.

## External anomaly-ranking experiment

To address RQ5, the committed external-validation artifact uses the
CIC-IDS2017 Friday afternoon DDoS flow file (Sharafaldin et al. 2018).
It contains 225,745 rows: 97,718 benign and 128,027 DDoS. With random
seed 47, the protocol draws a 12,000-row benign-only reference set and
evaluates a balanced test set of 6,000 benign and 6,000 DDoS flows.
Preprocessing and variable-feature selection use only the benign
reference. Methods are ranked continuously and evaluated at a top-10%
alert budget.

The compared methods are robust multivariate deviation, Isolation
Forest, Local Outlier Factor (LOF), and a PhiGraph relational score
combining robust deviation, mean nearest-neighbor distance, and
disagreement between their percentile ranks. Table
[2](#tab:cicids){reference-type="ref" reference="tab:cicids"} reproduces
the committed result.

::: {#tab:cicids}
  Method                   ROC-AUC   PR-AUC    P@10%    R@10%   F1@10%   Time (s)
  ---------------------- --------- -------- -------- -------- -------- ----------
  Local Outlier Factor      0.9757   0.9506   0.9617   0.1923   0.3206      0.322
  PhiGraph relational       0.7295   0.7316   0.8400   0.1680   0.2800      0.165
  Isolation Forest          0.7403   0.6840   0.7817   0.1563   0.2606      0.321
  Robust deviation          0.5771   0.5540   0.4117   0.0823   0.1372      0.006

  : CIC-IDS2017 Friday DDoS anomaly-ranking results. Runtime is reported
  by the committed validation artifact; its execution environment was
  not recorded.
:::

<figure id="fig:cicids-bars" data-latex-placement="H">

<figcaption>PR-AUC and precision at a 10% alert budget for each method
on the CIC-IDS2017 Friday DDoS experiment (same run as Table <a
href="#tab:cicids" data-reference-type="ref"
data-reference="tab:cicids">2</a>). Local Outlier Factor dominates on
both metrics; the PhiGraph relational score ranks second, ahead of
Isolation Forest and robust deviation.</figcaption>
</figure>

LOF is clearly strongest on this experiment. PhiGraph is second by
PR-AUC and precision at budget, but its ROC-AUC is slightly below
Isolation Forest. This single fixed experiment establishes only that the
implementation produces a non-degenerate ranking under the reported
protocol. It does not support a claim of general or state-of-the-art
superiority.

# Threats to Validity and Limitations

#### Dataset validity.

CIC-IDS2017 has documented problems in flow construction, feature
generation, and labels (Liu et al. 2022; Lanvin et al. 2022). Results
may change on corrected data. The machine-learning CSV also omits source
and destination IP addresses, timestamps, users, devices, and processes.
The evaluated graph is therefore a feature-similarity graph rather than
the heterogeneous operational graph for which PhiGraph is designed.

#### Experimental validity.

The external result uses one file, one attack family, one seed, and one
alert budget. It reports no uncertainty intervals, ablation confidence
intervals, or prospective evaluation. The benchmark is balanced and does
not reproduce a production base rate. The PhiGraph score is
batch-transductive because its component percentile ranks are calculated
over the complete evaluation batch; scores can therefore change with
batch composition and are not calibrated online anomaly scores.
Additional chronological splits, repeated seeds, corrected datasets,
heterogeneous event sources, and cost-sensitive metrics are required.

#### Software validity.

Automated tests can encode incorrect assumptions and do not substitute
for penetration testing, formal verification, independent replication,
or operational incident analysis. The ledger's hash chain detects
accidental or unauthorized changes only under an appropriate trust and
key-management model. JSON and SQLite are evaluation backends;
production use requires hardened storage, secrets management,
authorization, monitoring, and backup procedures.

#### Transactional ledger validity.

The scoped transactional API is implemented for JSON (single-process
staging) and SQLite (`BEGIN IMMEDIATE`). JSON rejects multiprocess
transactional mode fail-closed. A PostgreSQL backend with the same
semantics is specified but not shipped in Core 4.1.0-rc.6. Contract
tests establish integrity checks for the released backends; they do not
prove Byzantine fault tolerance or safety under a compromised signing
key and unrestricted storage access.

#### GRDI and replay validity.

GRDI records a shadow decision chain with explicit `NOT_EXECUTED`
invariants. Replay audit verifies persisted structure and signatures
without re-running simulation or authority evaluation. Historical
comparison reports structural differences only; it does not establish
causal improvement, semantic equivalence across deployments, or
correctness of shadow simulations. External connectors and live
execution remain out of scope.

#### HAV validity.

HAV's claim extractor is pattern- and rule-based, not a trained language
or entailment model; its structured extractor recognizes a fixed
vocabulary of repository-status phrasing in English and Spanish, and its
factual extractor flags generic percentage, date, quantity, and
attribution patterns without grounding them. Recall and precision on
naturally occurring agent output are therefore unmeasured, and the three
scenarios in Section [5.3](#sec:hav-scenarios){reference-type="ref"
reference="sec:hav-scenarios"} are illustrative confirmations of policy
logic, not a benchmark. Verification only compares extracted claims to
caller-supplied evidence; HAV does not independently retrieve or
authenticate that evidence, so an incorrect or manipulated authoritative
state can still produce an incorrect verdict. Multi-output consistency
checking is a lexical overlap heuristic and is explicitly documented as
an auxiliary signal rather than proof of factual agreement.

#### Causal and governance claims.

Graph connectivity, spectral structure, and anomaly scores do not
identify causal effects without assumptions and suitable interventions.
PhiGraph records candidate causal pathways but does not prove causality
from observational data. Likewise, a recorded approval may still be
mistaken or malicious. The platform improves inspectability and
enforcement points; it does not guarantee ethical, legal, or correct
outcomes.

# Reproducibility and Availability

PhiGraph Core 4.1.0-rc.6 is implemented in Python and distributed under
the MIT License. Its development repository is maintained at
<https://github.com/wcalmels/phigraph>. The v2 draft described here
corresponds to Git commit `a5a7187` on `main`. This paper is archived on
Zenodo at <https://doi.org/10.5281/zenodo.21689514> (v1); a new version
upload will supersede the PDF while retaining the same DOI. The paper
source and references are licensed under CC BY 4.0.

The software test suite can be reproduced with:

    python -m venv .venv
    pip install -e ".[api,benchmark,dev,auth,app]"
    pytest

Scoped transactional contract tests:

    pytest tests/contract/test_transactional_*.py

The HAV-specific tests can be run in isolation with:

    pytest tests/test_hav_core_integration.py tests/test_hav_api.py \
           tests/test_hav_v02_connectors.py \
           tests/test_hav_v02_factual_consistency.py \
           tests/test_hav_v02_benchmark.py \
           tests/test_hav_v02_api_security.py

The CIC-IDS2017 experiment requires the Friday DDoS CSV and is run with:

    python scripts/validate_cicids2017.py /path/to/Friday...DDos.csv

The committed validation artifact records metrics and predictions but
does not record the source-dataset checksum, exact dependency versions,
hardware, operating system, or Git revision. It is therefore an
auditable result artifact, not yet an exact reproducibility package. A
final archive should preserve the dataset provenance and checksum,
Python and dependency versions, seed, configuration, hardware
description, and Git revision. The archival record is available at
<https://doi.org/10.5281/zenodo.21689514>.

# Ethical and Operational Considerations

PhiGraph can store sensitive evidence, identity metadata, and
operational proposals. Deployers must minimize collection, define
retention periods, encrypt transport and storage, separate tenant
access, protect signing keys, and audit privileged operations. Security
telemetry and network datasets may contain personal or confidential
information and require an appropriate legal basis. The system should be
evaluated in replay or shadow mode before any higher-authority
integration. Human approval should remain mandatory where consequences
are difficult to reverse or affect safety, rights, employment, finance,
health, or critical infrastructure.

# Conclusion

PhiGraph makes a specific architectural choice: intelligence does not
imply authority. Claims must remain linked to evidence and verification;
actions must remain subject to policy and explicit execution boundaries;
outcomes must remain auditable. Core 4.1.0-rc.6 demonstrates this design
through a typed protocol, tamper-evident ledger, scoped transactional
store, GRDI shadow decision chain, policy-gated runtime, scope-tagged
records, and an automated test suite of 319 cases. HAV v0.2 extends the
same design to a concrete instance of the problem: it treats
agent-generated status claims as unverified until checked against an
explicitly supplied authoritative state, and it fails closed, rather
than open, when that state is unavailable. The external CIC-IDS2017
experiment shows a functional relational anomaly score but also
illustrates why bounded interpretation is necessary: a conventional LOF
baseline performs best, and the dataset cannot exercise PhiGraph's full
heterogeneous graph model. Future work should prioritize independent
replication, corrected and chronological security datasets, multi-source
operational graphs, a trained or retrieval-based claim extractor
evaluated against a labeled corpus, policy-adversarial testing,
cryptographically anchored audit storage, and prospective shadow
deployments.

# Author Contributions {#author-contributions .unnumbered}

Walter Calmels von Dem Knesebeck conceived the system, implemented the
software, designed the evaluation, analyzed the results, and wrote the
manuscript.

# Conflict of Interest {#conflict-of-interest .unnumbered}

The author is affiliated with TUCH Systems, the organization developing
PhiGraph. This relationship may create a commercial interest in the
system. The evaluation and limitations are reported to enable
independent scrutiny.

# License {#license .unnumbered}

This paper is licensed under the Creative Commons Attribution 4.0
International License (CC BY 4.0).

::::::::::::::: {#refs .references .csl-bib-body .hanging-indent}
::: {#ref-battaglia2018relational .csl-entry}
[Battaglia, Peter W., Jessica B. Hamrick, Victor Bapst, et al.]{.nocase}
2018. "Relational Inductive Biases, Deep Learning, and Graph Networks."
*arXiv Preprint arXiv:1806.01261*, ahead of print.
<https://doi.org/10.48550/arXiv.1806.01261>.
:::

::: {#ref-gebru2021datasheets .csl-entry}
Gebru, Timnit, Jamie Morgenstern, Briana Vecchione, et al. 2021.
"Datasheets for Datasets." *Communications of the ACM* 64 (12): 86--92.
<https://doi.org/10.1145/3458723>.
:::

::: {#ref-ji2023hallucination .csl-entry}
Ji, Ziwei, Nayeon Lee, Rita Frieske, et al. 2023. "Survey of
Hallucination in Natural Language Generation." *ACM Computing Surveys*
55 (12): 1--38. <https://doi.org/10.1145/3571730>.
:::

::: {#ref-lanvin2022errors .csl-entry}
Lanvin, Maxime, Pierre-François Gimenez, Yufei Han, Frédéric Majorczyk,
Ludovic Mé, and Éric Totel. 2022. "Errors in the CICIDS2017 Dataset and
the Significant Differences in Detection Performances It Makes." *Risks
and Security of Internet and Systems*, 18--33.
<https://doi.org/10.1007/978-3-031-31108-6_2>.
:::

::: {#ref-lebo2013provo .csl-entry}
Lebo, Timothy, Satya Sahoo, and Deborah McGuinness. 2013. *PROV-O: The
PROV Ontology*. {W3C} Recommendation. World Wide Web Consortium.
<https://www.w3.org/TR/prov-o/>.
:::

::: {#ref-liu2022errors .csl-entry}
Liu, Lisa, Gints Engelen, Timothy Lynar, Daryl Essam, and Wouter Joosen.
2022. "Error Prevalence in NIDS Datasets: A Case Study on CIC-IDS-2017
and CSE-CIC-IDS-2018." *2022 IEEE Conference on Communications and
Network Security*, 254--62.
<https://doi.org/10.1109/CNS56114.2022.9947235>.
:::

::: {#ref-mitchell2019modelcards .csl-entry}
Mitchell, Margaret, Simone Wu, Andrew Zaldivar, et al. 2019. "Model
Cards for Model Reporting." *Proceedings of the Conference on Fairness,
Accountability, and Transparency*, 220--29.
<https://doi.org/10.1145/3287560.3287596>.
:::

::: {#ref-owasp2025agentic .csl-entry}
OWASP Agentic Security Initiative. 2025. *Agentic AI: Threats and
Mitigations*. OWASP Foundation.
<https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/>.
:::

::: {#ref-sharafaldin2018cicids .csl-entry}
Sharafaldin, Iman, Arash Habibi Lashkari, and Ali A. Ghorbani. 2018.
"Toward Generating a New Intrusion Detection Dataset and Intrusion
Traffic Characterization." *Proceedings of the 4th International
Conference on Information Systems Security and Privacy*, 108--16.
<https://doi.org/10.5220/0006639801080116>.
:::

::: {#ref-nist2023airmf .csl-entry}
Tabassi, Elham. 2023. *Artificial Intelligence Risk Management Framework
(AI RMF 1.0)*. NIST AI 100-1. National Institute of Standards;
Technology. <https://doi.org/10.6028/NIST.AI.100-1>.
:::

::: {#ref-thorne2018fever .csl-entry}
Thorne, James, Andreas Vlachos, Christos Christodoulopoulos, and Arpit
Mittal. 2018. "FEVER: A Large-Scale Dataset for Fact Extraction and
VERification." *Proceedings of the 2018 Conference of the North American
Chapter of the Association for Computational Linguistics: Human Language
Technologies, Volume 1 (Long Papers)*, 809--19.
<https://doi.org/10.18653/v1/N18-1074>.
:::

::: {#ref-torresarias2019intoto .csl-entry}
Torres-Arias, Santiago, Hammad Afzali, Trishank Karthik Kuppusamy, Reza
Curtmola, and Justin Cappos. 2019. "In-Toto: Providing Farm-to-Table
Guarantees for Bits and Bytes." *28th USENIX Security Symposium*,
1393--410.
<https://www.usenix.org/conference/usenixsecurity19/presentation/torres-arias>.
:::
:::::::::::::::
