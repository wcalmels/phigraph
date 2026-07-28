# PhiGraph v1.3 Production Readiness & Kernel Ensemble

Version 1.3 adds production controls rather than unrestricted autonomy.

## Components

- DataContractAgent
- DriftDetectionAgent
- KernelCriticAgent with kernel ensemble
- CalibrationAgent
- EvidenceFusionAgent
- SafetyGateAgent
- ProductionReadinessAgent
- ShadowModeRunner

## Decision states

- ACCEPT
- ACCEPT_WITH_REVIEW
- INSUFFICIENT_EVIDENCE
- BLOCKED_BY_DATA
- BLOCKED_BY_DRIFT
- BLOCKED_BY_EVIDENCE

No operational action is executed automatically. The highest autonomy level
requires human approval and rollback availability.
