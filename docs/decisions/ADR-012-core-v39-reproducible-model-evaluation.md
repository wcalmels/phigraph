# ADR-012 — Reproducible model evaluation

## Status
Accepted for v3.9.0.

## Context
PhiGraph required direct model integration and repeatable evidence without granting repository write authority or accepting self-reported cost, latency, tests, or completion claims.

## Decision
Adopt versioned JSONL corpora, provider-neutral adapters with measured usage, read-only commit archives, isolated patch evaluation, deterministic security/dependency evidence, explicit quality gates, repeated runs, and machine-readable reports.

## Consequences
The platform can compare models more rigorously. Provider calls remain opt-in and configurable. Deterministic scanning remains deliberately limited and must not be represented as comprehensive SAST or supply-chain assurance.
