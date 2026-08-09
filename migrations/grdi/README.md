# GRDI persistence migrations

GRDI extends the Core ledger with scoped collections. No SQL schema migration is
required for the generic SQLite/PostgreSQL ledger tables.

## Collections by increment

| Increment | Collections added |
|---|---|
| Foundation v0.1 | `decision_envelopes`, `authority_decisions` |
| Execution Gateway v0.2 | `execution_requests`, `gateway_decisions`, `shadow_execution_receipts` |
| Outcome Ledger v0.3 | `shadow_outcomes` |

## Compatibility

- JSON ledgers initialize absent collections on read.
- SQLite and PostgreSQL store collection names and JSON payloads in existing
  generic ledger tables.
- Operators should back up the ledger before upgrading and validate the hash
  chain after deployment.

## Operational notes

- Outcome recording enforces one row per `shadow_receipt_id` with the in-process
  ledger lock.
- Multi-node uniqueness for outcomes requires a future transactional backend
  constraint, similar to shadow simulation receipts.
