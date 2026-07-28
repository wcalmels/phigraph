CREATE TABLE IF NOT EXISTS phigraph_core_ledger (
    collection TEXT NOT NULL,
    record_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    project_id TEXT NOT NULL DEFAULT 'default',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (collection, record_id)
);
CREATE INDEX IF NOT EXISTS idx_phigraph_core_scope
ON phigraph_core_ledger (tenant_id, project_id, collection);
