-- PhiGraph scoped transactional ledger v2 (GRDI gateway decision events)
-- Forward-only. Updates partial chain index to include gateway_decision_events.
-- Does not modify historical rows.

DROP INDEX IF EXISTS uq_scoped_chain_sequence_linked;

CREATE UNIQUE INDEX uq_scoped_chain_sequence_linked
    ON phigraph_scoped_ledger (tenant_id, project_id, collection, chain_sequence)
    WHERE collection IN (
        'decision_envelopes',
        'authority_decisions',
        'execution_requests',
        'gateway_decisions',
        'gateway_decision_events',
        'shadow_execution_receipts',
        'shadow_outcomes',
        'replay_reports',
        'historical_comparisons'
    );
