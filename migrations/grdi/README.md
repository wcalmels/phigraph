# GRDI Foundation persistence

GRDI Foundation v0.1 adds the logical ledger collections
`decision_envelopes` and `authority_decisions`.

No SQL schema migration is required. The JSON backend initializes absent
collections compatibly, while SQLite and PostgreSQL store collection names and
record payloads in their existing generic ledger tables. Existing ledgers remain
readable and receive the new empty collections on first use.

Operators should still back up the ledger before upgrading and validate the
hash chain after deployment.
