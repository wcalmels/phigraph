# PhiGraph Core v3.0 Architecture

## Status

Initial canonical implementation. PhiGraph Core v3 consolidates the existing analytical, governance, shadow and controlled-execution capabilities behind a provider-neutral protocol.

## Architectural principle

An AI or deterministic agent output is a proposal, not a fact or an authorized action.

```text
Agent / LLM / workflow
        |
        v
Claims and action proposals
        |
        v
Evidence Ledger -> Verification Engine -> Policy Engine
        |                                      |
        +----------------------+---------------+
                               v
                 Replay / Shadow / Copilot / Guarded Auto
                               |
                               v
                         Outcomes and feedback
```

## Canonical modules

1. **Core Protocol** — typed claims, evidence, verifications, actions, decisions and outcomes.
2. **Evidence Ledger** — append-oriented provenance store with deterministic content hashes.
3. **Verification Engine** — provider-independent verifier registry.
4. **Policy Engine** — allow, warn, require approval or block.
5. **Shadow Runtime** — simulation by default; no external execution.
6. **Agent Adapter API** — neutral interface for LLMs, local models and deterministic agents.
7. **Domain Packages** — Cyber, Code, Logistics and future verticals.

## Runtime modes

- `replay`: historical evaluation only.
- `shadow`: live observation, no execution.
- `copilot`: authorized execution through an explicit executor.
- `guarded_auto`: policy-controlled automation through an explicit executor.

The core never receives an implicit executor. This prevents accidental transition from observation to action.

## Compatibility

The v2.2.3 packages remain available. Core v3 is introduced as `phigraph.core_v3` so existing imports and tests continue to work while modules are progressively migrated.

## Non-claims

Core v3 does not claim to eliminate hallucinations, prove causality from observational data or guarantee error-free autonomous operation. It reduces the probability that unsupported claims or unauthorized actions are accepted as valid.
