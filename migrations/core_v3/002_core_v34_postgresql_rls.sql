-- PhiGraph Core v3.4 optional PostgreSQL row-level security.
ALTER TABLE IF EXISTS phigraph_core_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS phigraph_core_ledger FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS phigraph_tenant_project_isolation ON phigraph_core_ledger;
CREATE POLICY phigraph_tenant_project_isolation ON phigraph_core_ledger
USING (
  tenant_id = current_setting('phigraph.tenant_id', true)
  AND project_id = current_setting('phigraph.project_id', true)
)
WITH CHECK (
  tenant_id = current_setting('phigraph.tenant_id', true)
  AND project_id = current_setting('phigraph.project_id', true)
);
-- The application connection must SET LOCAL phigraph.tenant_id/project_id per transaction.
