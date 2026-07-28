# ADR-002: Shadow is the default operational mode

- **Status:** Accepted
- **Date:** 2026-07-27

## Decision

Core v3 defaults to shadow mode. Replay and shadow cannot execute external actions. Copilot and guarded-auto require an explicit executor and an allowing policy decision.

## Rationale

Authority must be earned through evidence, validation and policy rather than inferred from model output.
