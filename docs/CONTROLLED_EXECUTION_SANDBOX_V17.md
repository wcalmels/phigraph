# PhiGraph v1.7 Controlled Execution Sandbox

Version 1.7 introduces a simulated execution boundary.

## Controls

- fake connectors only;
- dry-run enforcement;
- idempotency keys;
- dual approval from distinct roles;
- rollback-plan validation;
- simulated rollback;
- governance and readiness checks;
- full execution receipt.

## Guarantee

This version never modifies a real external system. Connectors generate simulated
references only, execution receipts always report `executed = false`, and
rollback receipts are simulations.
