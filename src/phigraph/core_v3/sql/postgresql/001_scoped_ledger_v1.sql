-- PhiGraph scoped transactional ledger v1 (ADR-021 / protocol 0.2.0)
-- Forward-only. Roll back via database restore, not partial revert.

CREATE TABLE IF NOT EXISTS phigraph_schema_migrations (
    version     TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS phigraph_scoped_ledger (
    tenant_id       TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    collection      TEXT NOT NULL,
    canonical_key   TEXT NOT NULL,
    record_id       TEXT NOT NULL,
    payload         JSONB NOT NULL,
    payload_hash    TEXT NOT NULL,
    chain_prev      TEXT,
    chain_hash      TEXT NOT NULL,
    chain_sequence  BIGINT NOT NULL,
    row_version     BIGINT NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, project_id, collection, canonical_key),
    UNIQUE (tenant_id, project_id, collection, record_id)
);

CREATE TABLE IF NOT EXISTS phigraph_chain_heads (
    tenant_id        TEXT NOT NULL,
    project_id       TEXT NOT NULL,
    collection       TEXT NOT NULL,
    last_sequence    BIGINT NOT NULL DEFAULT 0,
    last_chain_hash  TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, project_id, collection)
);

CREATE INDEX IF NOT EXISTS idx_scoped_scope_collection
    ON phigraph_scoped_ledger (tenant_id, project_id, collection);

CREATE INDEX IF NOT EXISTS idx_scoped_chain_sequence
    ON phigraph_scoped_ledger (tenant_id, project_id, collection, chain_sequence);

CREATE INDEX IF NOT EXISTS idx_scoped_record_id
    ON phigraph_scoped_ledger (tenant_id, project_id, collection, record_id);

CREATE INDEX IF NOT EXISTS idx_chain_heads_scope
    ON phigraph_chain_heads (tenant_id, project_id, collection);

CREATE UNIQUE INDEX IF NOT EXISTS uq_scoped_chain_sequence_linked
    ON phigraph_scoped_ledger (tenant_id, project_id, collection, chain_sequence)
    WHERE collection IN (
        'decision_envelopes',
        'authority_decisions',
        'execution_requests',
        'gateway_decisions',
        'shadow_execution_receipts',
        'shadow_outcomes',
        'replay_reports',
        'historical_comparisons'
    );
