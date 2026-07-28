# PhiGraph Core v3.9 — Reproducible Model Evaluation

## Purpose

v3.9 moves PhiGraph Code from a patch-evaluation harness toward a reproducible experimental platform. A benchmark is bound to a task corpus, repository, commit, model configuration, checks, repetitions, measured token use, cost, latency, and deterministic quality gates.

## Flow

```text
versioned corpus
→ commit snapshot / read-only archive
→ model adapter
→ canonical patch proposal
→ isolated temporary repository
→ compile/tests/lint/typecheck
→ security and dependency evidence
→ quality decision
→ repeated measurements
→ JSON and Markdown report
```

## Core components

- `ReproducibleCorpus`: JSONL corpus with deterministic SHA-256.
- `OpenAICompatibleModelAdapter`: provider-neutral, injectable transport, token/cost/latency measurement.
- `GitHubCommitArchiveFetcher`: GET-only archive acquisition with safe extraction.
- `DeterministicSecurityScanner`: narrow, auditable benchmark gate; not a full SAST replacement.
- `DependencyInventory`: declared dependency inventory without dependency resolution.
- `PatchQualityEvaluator`: combines isolated checks, patch size, binary-file and introduced-security gates.
- `CorpusExperimentRunner`: repeated evaluations over a fixed corpus.
- `save_scientific_report`: reproducible JSON and Markdown artifacts.

## Interpretation

Results are valid only for the declared corpus, commits, checks, model/provider configuration and number of repetitions. They do not prove general superiority or eliminate software defects.
