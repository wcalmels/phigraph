# PhiGraph Core 4.1.0-rc.2 — GRDI Foundation v1

## Implemented

- Decision Envelope protocol and persistence.
- Fail-closed Authority Engine.
- Signed HAV receipt verification and tenant/project scope binding.
- Separate verification, authorization, executability, and execution states.
- Scoped idempotent `/v4/grdi` API.
- Append-only authority decisions in the Core ledger.

## Limitations

- Execution Gateway: `CONCEPTUAL`.
- Outcome Ledger: `CONCEPTUAL`.
- Replay across GRDI decisions: `CONCEPTUAL`.
- External actions remain disabled.
- Authorized envelopes remain `NOT_EXECUTABLE` and `NOT_EXECUTED`.
