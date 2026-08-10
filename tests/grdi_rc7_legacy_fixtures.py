"""RC7-style legacy GRDI rows for cutover tests (legacy storage only, no scoped sidecar)."""

from __future__ import annotations

from typing import Any

from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.receipts import ReceiptSigner
from phigraph.grdi import (
    AuthorityEngine,
    ExecutionGateway,
    ExecutionRequest,
    ShadowSimulationState,
    action_hash,
)
from test_grdi_foundation import _envelope, _receipt

RC7_DECIDED_AT = "2026-07-29T12:00:00+00:00"
RC7_SIMULATED_AT = "2026-07-29T12:01:00+00:00"


def register_rc7_simulated_plan(
    ledger: EvidenceLedger,
    signer: ReceiptSigner,
    *,
    tenant_id: str = "tenant-a",
    project_id: str = "project-a",
) -> str:
    """Seed a fully simulated plan into legacy ledger arrays/tables only."""
    envelope = _envelope(
        signer,
        tenant_id=tenant_id,
        project_id=project_id,
        hav_receipt=_receipt(signer, tenant_id=tenant_id, project_id=project_id),
    )
    authority = AuthorityEngine(signer).evaluate(
        envelope,
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    requested_action = envelope.proposed_action
    request = ExecutionRequest.create(
        envelope_id=envelope.envelope_id,
        authority_decision_id=authority.authority_decision_id,
        tenant_id=tenant_id,
        project_id=project_id,
        requested_by="operator-rc7",
        requested_action=requested_action,
        action_hash=action_hash(requested_action),
        expected_effects=("staging promotion recorded",),
        rollback_strategy={"type": "revert_release", "target": "previous"},
        created_at=RC7_DECIDED_AT,
    )
    gateway = ExecutionGateway(signer).evaluate(
        envelope=envelope,
        authority=authority,
        request=request,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    gateway_row = gateway.to_dict()
    gateway_row["decided_at"] = RC7_DECIDED_AT
    gateway_row["simulation_state"] = ShadowSimulationState.SIMULATED.value

    receipt = ExecutionGateway(signer).simulate(
        envelope=envelope,
        authority=authority,
        request=request,
        gateway=gateway,
    )
    receipt_row = receipt.to_dict()
    receipt_row["simulated_at"] = RC7_SIMULATED_AT

    _register(ledger, "decision_envelopes", envelope.to_dict(), "envelope_id", tenant_id, project_id)
    _register(ledger, "authority_decisions", authority.to_dict(), "authority_decision_id", tenant_id, project_id)
    _register(ledger, "execution_requests", request.to_dict(), "plan_id", tenant_id, project_id)
    _register(ledger, "gateway_decisions", gateway_row, "gateway_decision_id", tenant_id, project_id)
    _register(ledger, "shadow_execution_receipts", receipt_row, "receipt_id", tenant_id, project_id)
    return request.plan_id


def register_rc7_mutable_simulated_without_receipt(
    ledger: EvidenceLedger,
    signer: ReceiptSigner,
    *,
    tenant_id: str = "tenant-a",
    project_id: str = "project-a",
) -> str:
    """Legacy row with mutable simulation_state but no verifiable receipt (fail-closed backfill)."""
    envelope = _envelope(
        signer,
        tenant_id=tenant_id,
        project_id=project_id,
        hav_receipt=_receipt(signer, tenant_id=tenant_id, project_id=project_id),
    )
    authority = AuthorityEngine(signer).evaluate(
        envelope,
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    requested_action = envelope.proposed_action
    request = ExecutionRequest.create(
        envelope_id=envelope.envelope_id,
        authority_decision_id=authority.authority_decision_id,
        tenant_id=tenant_id,
        project_id=project_id,
        requested_by="operator-rc7",
        requested_action=requested_action,
        action_hash=action_hash(requested_action),
        expected_effects=("staging promotion recorded",),
        rollback_strategy={"type": "revert_release", "target": "previous"},
        created_at=RC7_DECIDED_AT,
    )
    gateway = ExecutionGateway(signer).evaluate(
        envelope=envelope,
        authority=authority,
        request=request,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    gateway_row = gateway.to_dict()
    gateway_row["decided_at"] = RC7_DECIDED_AT
    gateway_row["simulation_state"] = ShadowSimulationState.SIMULATED.value

    _register(ledger, "decision_envelopes", envelope.to_dict(), "envelope_id", tenant_id, project_id)
    _register(ledger, "authority_decisions", authority.to_dict(), "authority_decision_id", tenant_id, project_id)
    _register(ledger, "execution_requests", request.to_dict(), "plan_id", tenant_id, project_id)
    _register(ledger, "gateway_decisions", gateway_row, "gateway_decision_id", tenant_id, project_id)
    return request.plan_id


def _register(
    ledger: EvidenceLedger,
    collection: str,
    row: dict[str, Any],
    unique_key: str,
    tenant_id: str,
    project_id: str,
) -> None:
    ledger.register_scoped_record(
        collection,
        row,
        unique_key=unique_key,
        tenant_id=tenant_id,
        project_id=project_id,
    )
