-- Server-side staging marker created during provisioning (not by the fixture loader).
CREATE TABLE IF NOT EXISTS phigraph_environment_metadata (
    environment TEXT NOT NULL,
    environment_id UUID NOT NULL,
    fixture_loading_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    provisioned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT phigraph_environment_metadata_single_row CHECK (environment_id IS NOT NULL),
    CONSTRAINT phigraph_environment_metadata_environment_lowercase CHECK (environment = lower(environment))
);

-- Exactly one row is enforced at application/provisioning time.
CREATE UNIQUE INDEX IF NOT EXISTS uq_phigraph_environment_metadata_singleton
    ON phigraph_environment_metadata ((TRUE));
