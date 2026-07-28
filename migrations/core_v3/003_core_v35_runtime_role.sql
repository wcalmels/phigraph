-- PhiGraph Core v3.5 runtime-role guidance.
-- Replace phigraph_runtime with the deployment-specific role.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'phigraph_runtime') THEN
        CREATE ROLE phigraph_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$;

GRANT SELECT, INSERT, UPDATE, DELETE ON phigraph_core_ledger TO phigraph_runtime;
ALTER TABLE phigraph_core_ledger FORCE ROW LEVEL SECURITY;
