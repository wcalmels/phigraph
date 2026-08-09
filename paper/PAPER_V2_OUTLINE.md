# PhiGraph Paper v2 — Outline and Publication Plan

**Branch:** `docs/paper-v2`  
**Base software:** `main@a5a7187` (Core 4.1.0-rc.6, GRDI 0.4.0)  
**Prior deposit:** Zenodo v1 — [10.5281/zenodo.21689514](https://doi.org/10.5281/zenodo.21689514)  
**Working title (draft):** *PhiGraph Core 4.1: Governed Relational Decision Intelligence with a Transactional Evidence Ledger*

---

## 1. Publication target (recommendation)

| Option | Scope | Effort | Recommendation |
|--------|-------|--------|----------------|
| **A. Zenodo v2 (primary)** | Update v1 LaTeX: architecture, GRDI stack, transactional ledger, test matrix, 3–4 new TikZ figures, revised abstract/limitations | **~1.5–2 weeks** | **Start here** — aligns repo DOI, investors, and reproducibility |
| **B. Long manuscript** | Option A + extended related work, formal threat model, appendix proofs, journal formatting | **+2–3 weeks** | Stretch goal after Zenodo v2 ships |
| **C. Split deposit** | Zenodo v2 = technical report; separate preprint for GRDI-only deep dive | Medium | Only if v2 exceeds ~25 pages |

**Decision:** pursue **Option A** on this branch; fold Option B content only if page budget allows without delaying the Zenodo update.

---

## 2. Version and status labels (mandatory in prose)

Use these labels consistently (mirror ADR / conformance reports):

| Label | Meaning in paper |
|-------|------------------|
| **Implemented** | Code on `main`, covered by automated tests |
| **Specified** | Protocol/ADR accepted; not fully implemented (e.g. PostgreSQL transactional backend) |
| **Evaluated** | Measured in CI or documented experiment with cited artifact |
| **Conjectured** | Design intent; no proof of safety or correctness |

**Headline facts (Implemented / Evaluated):**

- Core **4.1.0-rc.6** (development candidate)
- GRDI **0.4.0** shadow chain (envelope → authority → plan → gateway → receipt → outcome → replay)
- HAV **0.2.0** fail-closed verification module
- Transactional scoped ledger API (JSON single-process, SQLite multiprocess) + `verify_scoped_chain()`
- **319** automated tests (262 baseline + 57 contract), CI Python 3.10–3.13 + Security + package + docker

**Do not claim:**

- State-of-the-art anomaly detection (v1 LOF baseline stands)
- Safe autonomous execution or formal verification of policies
- Production PostgreSQL transactional semantics (Specified only)
- GRDI external execution or live connectors

---

## 3. Document structure (section map)

Legend: **Keep** = minor edits; **Revise** = rewrite; **New** = add section.

| § | Title | Action | Source material |
|---|-------|--------|-----------------|
| — | Abstract | **Revise** | ADR-016–020, RELEASE_NOTES_V4.1.0_RC6, conformance reports |
| — | Keywords | **Revise** | add *transactional ledger*, *GRDI*, *replay audit* |
| 1 | Introduction | **Revise** | shadow-first + agent governance gap; cite NIST AI RMF |
| 2 | Related Work | **Revise** | + provenance ledgers, workflow engines, policy-as-code (short) |
| 3 | System Model and Design Goals | **Keep/Revise** | fail-closed, scope isolation, shadow-default |
| 4 | PhiGraph Architecture | **Revise** | split Core / GRDI / HAV; Figure 1 update |
| 4.1 | Canonical protocol | **Keep** | Protocol 2.0.0 lifecycle; Figure 2 update |
| 4.2 | Evidence ledger (legacy) | **Revise** | point to scoped transactional store |
| **§4.3** | **Transactional scoped ledger** | **Done** | ADR-020, Fig. 6–7 |
| 4.4 | Policy-gated runtime | **Keep** | shadow vs execution modes |
| 4.5 | HAV v0.2 | **Keep** | Figures 3–4 unchanged unless auth scope text updates |
| **4.6** | **GRDI shadow decision chain** | **Done** | ADR-016–019, Fig. 8 |
| 4.7 | API, SDK, and operations | **Revise** | deployment boundaries, identity for HAV |
| 5 | Evaluation | **Revise** | restructure subsections |
| 5.1 | Research questions | **Revise** | RQ on integrity, idempotency, replay determinism |
| 5.2 | Software verification | **Revise** | 319 tests, CI matrix, contract tests |
| 5.3 | HAV verification scenarios | **Keep** | update counts if fixtures changed |
| **5.4** | **Transactional ledger integrity** | **New** | cite `tests/contract/test_transactional_*.py` |
| **5.5** | **GRDI replay audit scenarios** | **New** | replay/historical comparison tests |
| 5.6 | External anomaly-ranking experiment | **Keep** | Figure 5 + Table; no new claims |
| 6 | Threats to Validity and Limitations | **Revise** | RC status, JSON multiprocess, PostgreSQL gap |
| 7 | Reproducibility and Availability | **Revise** | new Zenodo v2 DOI, commit pin `a5a7187` |
| 8 | Ethical and Operational Considerations | **Keep** | light touch |
| 9 | Conclusion | **Revise** | governance substrate, not autonomous agent proof |
| — | Author / COI / License | **Keep** | CC BY 4.0 paper; MIT software |

---

## 4. Figures plan (TikZ/pgfplots only)

| Fig | v1 status | v2 action |
|-----|-----------|-----------|
| 1 Architecture | TikZ | **Update** — add GRDI + transactional store boxes |
| 2 Protocol lifecycle | TikZ | **Minor update** — label scoped collections |
| 3 HAV pipeline | TikZ | Keep |
| 4 HAV fail-closed flowchart | TikZ | Keep |
| 5 CIC-IDS2017 bars | pgfplots | Keep (same data) |
| **6 Scoped transaction** | — | **Done** |
| **7 Chain-linked vs mutable** | — | **Done** |
| **8 GRDI shadow pipeline** | — | **Done** |
| 9 (optional) `verify_scoped_chain` | — | **New** — fail-closed checks (missing head, gaps, tamper) |

All figures: `\usepackage{float}` + `[H]` placement (same as v1).

---

## 5. Claims matrix (what each section may assert)

### 5.1 Transactional ledger (§4.3, §5.4)

| Claim | Status | Evidence |
|-------|--------|----------|
| Atomic multi-append in one transaction (JSON/SQLite) | Implemented | `run_scoped_transaction` + contract tests |
| Idempotent `append_scoped_once` under concurrency | Implemented (SQLite) / single-process (JSON) | `test_transactional_sqlite.py` |
| Undeclared lock rejection | Implemented | `test_transactional_invariants.py` |
| CAS only on mutable Core collections | Implemented | ADR-020 + invariants tests |
| Fail-closed scoped chain verification | Implemented | `verify_scoped_chain` + 32 adversarial tests |
| PostgreSQL backend | Specified only | ADR-020 explicit non-goal in rc.6 |

### 5.2 GRDI (§4.6, §5.5)

| Claim | Status | Evidence |
|-------|--------|----------|
| Shadow execution gateway records simulation without external execution | Implemented | ADR-017, gateway tests |
| Outcome ledger links shadow receipts to outcomes | Implemented | ADR-018 |
| Replay audit compares persisted chain without re-simulation | Implemented | ADR-019, replay tests |
| Decision envelope + authority engine boundaries | Implemented | ADR-016 |

### 5.3 HAV (§4.5, §5.3)

| Claim | Status | Evidence |
|-------|--------|----------|
| Fail-closed verify against supplied authoritative state | Implemented | HAV tests + Figure 4 |
| Tenant/project from Core identity (not spoofable body) | Implemented | ADR-015 |

---

## 6. Writing workflow (suggested order)

1. **Restore & compile v1 baseline** on this branch (`pdflatex`/`bibtex` cycle) — confirm Figure 1–5 build.
2. **Draft §4.3 + Figures 6–7** (transactional ledger — highest novelty vs v1).
3. **Draft §4.6 + Figure 8** (GRDI stack on `main`).
4. **Rewrite abstract + §5.2 + §5.4 + §5.5** with test counts from `pytest --collect-only`.
5. **Revise §6 limitations** (RC, backends, no SOTA claim).
6. **Update `zenodo_metadata.json`** for v2 title/description/keywords (new version of record).
7. **Internal review** — cross-check every number against CI run on pinned commit.
8. **Zenodo upload** — new version linked to DOI 10.5281/zenodo.21689514.
9. **Tag repo** — e.g. `paper-v2.0` or align with `v4.1.0-rc.6` release notes.

---

## 7. Files to modify (checklist)

- [ ] `paper/main.tex` — body + new figures
- [ ] `paper/references.bib` — ADRs as `@misc`, any new citations
- [ ] `paper/README.md` — v2 build notes
- [ ] `paper/zenodo_metadata.json` — v2 metadata draft
- [ ] `paper/main.pdf` — rebuilt after LaTeX pass
- [ ] `CITATION.cff` / root `README.md` — after Zenodo v2 DOI published (separate commit)

---

## 8. Open decisions (resolve before full draft)

1. **Title:** keep “4.0” lineage vs rebrand to “4.1” in title (recommend **4.1** with footnote to v1 DOI).
2. **GRDI naming:** “Governed Relational Decision Intelligence” vs acronym-only — align with `docs/protocol/GRDI_PROTOCOL_V1.md`.
3. **Page target:** ~18–22 pages (Zenodo) vs ~30+ (journal) — drives Option A vs B.
4. **Author list:** unchanged unless new contributors join v2.

---

## 9. Next session prompt (for implementation)

> “Implement Paper v2 §4.3 and Figure 6 in `paper/main.tex` from `PAPER_V2_OUTLINE.md`, using ADR-020 and conformance report wording; keep all claims at Implemented/Evaluated level only.”
