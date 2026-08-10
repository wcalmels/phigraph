"""LockRef builders for GRDI scoped transactions."""

from __future__ import annotations

from phigraph.core_v3.transactions import LockKind, LockRef, gateway_event_canonical_key


def canonical_lock(
    collection: str,
    canonical_key: str,
    *,
    tenant_id: str,
    project_id: str,
) -> LockRef:
    return LockRef(
        tenant_id=tenant_id,
        project_id=project_id,
        collection=collection,
        kind=LockKind.CANONICAL,
        canonical_key=canonical_key,
    )


def chain_lock(collection: str, *, tenant_id: str, project_id: str) -> LockRef:
    return LockRef(
        tenant_id=tenant_id,
        project_id=project_id,
        collection=collection,
        kind=LockKind.CHAIN,
    )


def envelope_locks(*, envelope_id: str, tenant_id: str, project_id: str) -> tuple[LockRef, ...]:
    return (
        chain_lock("decision_envelopes", tenant_id=tenant_id, project_id=project_id),
        canonical_lock(
            "decision_envelopes",
            envelope_id,
            tenant_id=tenant_id,
            project_id=project_id,
        ),
    )


def authority_locks(
    *,
    envelope_id: str,
    authority_decision_id: str,
    tenant_id: str,
    project_id: str,
) -> tuple[LockRef, ...]:
    return (
        *envelope_locks(envelope_id=envelope_id, tenant_id=tenant_id, project_id=project_id),
        chain_lock("authority_decisions", tenant_id=tenant_id, project_id=project_id),
        canonical_lock(
            "authority_decisions",
            authority_decision_id,
            tenant_id=tenant_id,
            project_id=project_id,
        ),
    )


def execution_plan_locks(
    *,
    envelope_id: str,
    authority_decision_id: str,
    plan_id: str,
    tenant_id: str,
    project_id: str,
) -> tuple[LockRef, ...]:
    created_event_key = gateway_event_canonical_key(plan_id, "GATEWAY_DECISION_CREATED")
    return (
        *authority_locks(
            envelope_id=envelope_id,
            authority_decision_id=authority_decision_id,
            tenant_id=tenant_id,
            project_id=project_id,
        ),
        chain_lock("execution_requests", tenant_id=tenant_id, project_id=project_id),
        canonical_lock("execution_requests", plan_id, tenant_id=tenant_id, project_id=project_id),
        chain_lock("gateway_decisions", tenant_id=tenant_id, project_id=project_id),
        canonical_lock("gateway_decisions", plan_id, tenant_id=tenant_id, project_id=project_id),
        chain_lock("gateway_decision_events", tenant_id=tenant_id, project_id=project_id),
        canonical_lock(
            "gateway_decision_events",
            created_event_key,
            tenant_id=tenant_id,
            project_id=project_id,
        ),
    )


def simulation_locks(
    *,
    plan_id: str,
    authority_decision_id: str,
    tenant_id: str,
    project_id: str,
) -> tuple[LockRef, ...]:
    simulation_event_key = gateway_event_canonical_key(plan_id, "SIMULATION_RECORDED")
    return (
        canonical_lock("execution_requests", plan_id, tenant_id=tenant_id, project_id=project_id),
        canonical_lock("gateway_decisions", plan_id, tenant_id=tenant_id, project_id=project_id),
        canonical_lock(
            "authority_decisions",
            authority_decision_id,
            tenant_id=tenant_id,
            project_id=project_id,
        ),
        chain_lock("shadow_execution_receipts", tenant_id=tenant_id, project_id=project_id),
        canonical_lock(
            "shadow_execution_receipts",
            plan_id,
            tenant_id=tenant_id,
            project_id=project_id,
        ),
        chain_lock("gateway_decision_events", tenant_id=tenant_id, project_id=project_id),
        canonical_lock(
            "gateway_decision_events",
            simulation_event_key,
            tenant_id=tenant_id,
            project_id=project_id,
        ),
    )


def outcome_locks(
    *,
    plan_id: str,
    shadow_receipt_id: str,
    tenant_id: str,
    project_id: str,
) -> tuple[LockRef, ...]:
    return (
        canonical_lock("execution_requests", plan_id, tenant_id=tenant_id, project_id=project_id),
        canonical_lock("gateway_decisions", plan_id, tenant_id=tenant_id, project_id=project_id),
        canonical_lock(
            "shadow_execution_receipts",
            plan_id,
            tenant_id=tenant_id,
            project_id=project_id,
        ),
        chain_lock("shadow_outcomes", tenant_id=tenant_id, project_id=project_id),
        canonical_lock(
            "shadow_outcomes",
            shadow_receipt_id,
            tenant_id=tenant_id,
            project_id=project_id,
        ),
    )


def replay_locks(*, plan_id: str, manifest_hash: str, tenant_id: str, project_id: str) -> tuple[LockRef, ...]:
    return (
        canonical_lock("execution_requests", plan_id, tenant_id=tenant_id, project_id=project_id),
        chain_lock("replay_reports", tenant_id=tenant_id, project_id=project_id),
        canonical_lock("replay_reports", manifest_hash, tenant_id=tenant_id, project_id=project_id),
    )


def comparison_locks(
    *,
    baseline_manifest_hash: str,
    candidate_manifest_hash: str,
    comparison_key: str,
    tenant_id: str,
    project_id: str,
) -> tuple[LockRef, ...]:
    return (
        canonical_lock(
            "replay_reports",
            baseline_manifest_hash,
            tenant_id=tenant_id,
            project_id=project_id,
        ),
        canonical_lock(
            "replay_reports",
            candidate_manifest_hash,
            tenant_id=tenant_id,
            project_id=project_id,
        ),
        chain_lock("historical_comparisons", tenant_id=tenant_id, project_id=project_id),
        canonical_lock(
            "historical_comparisons",
            comparison_key,
            tenant_id=tenant_id,
            project_id=project_id,
        ),
    )
