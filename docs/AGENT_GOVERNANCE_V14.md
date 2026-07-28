# PhiGraph v1.4 Agent Governance & Consensus

Version 1.4 adds formal governance over the production-readiness pipeline.

## Capabilities

- weighted agent roles;
- required-agent checks;
- safety and data vetoes;
- contradiction detection;
- consensus states;
- human-review dossier;
- persistent decision audit.

## Consensus states

- ACCEPT
- ACCEPT_WITH_REVIEW
- INSUFFICIENT_EVIDENCE
- REJECT

The governance layer cannot execute operational actions. It records the
decision, rationale, contradictions, proposed action, success criteria, and
rollback criteria for human review.
