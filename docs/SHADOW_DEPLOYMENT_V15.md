# PhiGraph v1.5 Shadow Deployment

Version 1.5 introduces non-intrusive operational evaluation.

## Capabilities

- governed shadow recommendations;
- guaranteed `executed = false`;
- operator feedback and accept/reject decisions;
- delayed real-outcome registration;
- precision, false-positive, acceptance and utility metrics;
- historical replay across ordered windows;
- persistent shadow deployment store.

## Principle

Shadow mode observes, recommends and records. It never modifies the real
operation. Promotion beyond shadow mode requires measured performance,
calibration, governance approval and rollback readiness.
