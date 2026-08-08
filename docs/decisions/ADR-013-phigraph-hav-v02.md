# ADR-013 — PhiGraph HAV v0.2 component integration

HAV capabilities are integrated as Core-compatible modules instead of importing standalone projects wholesale.

Included: connectors, factual extraction, consistency signal, provider abstraction, benchmark runner, optional API key and fail-closed handling.

Excluded: generated-code execution, embedded SQLite audit database, unauthenticated Flask API, ungoverned web search and synthetic fallback metrics.
