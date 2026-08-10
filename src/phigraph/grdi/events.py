"""Deterministic gateway decision events (GRDI Gateway Events protocol v0.1.0)."""

from __future__ import annotations

import uuid
from typing import Any

from phigraph.core_v3.transactions import gateway_event_canonical_key
from phigraph.version import GRDI_GATEWAY_EVENTS_PROTOCOL_VERSION

GRDI_EVENT_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://phi47.cl/grdi/gateway-decision-events/v0.1.0",
)


def deterministic_event_id(
    *,
    tenant_id: str,
    project_id: str,
    plan_id: str,
    event_type: str,
) -> str:
    name = f"{tenant_id}/{project_id}/{plan_id}:{event_type}"
    return str(uuid.uuid5(GRDI_EVENT_NAMESPACE, name))


def build_gateway_decision_event_record(
    *,
    tenant_id: str,
    project_id: str,
    plan_id: str,
    gateway_decision_id: str,
    event_type: str,
    occurred_at: str,
    source_record_id: str = "",
    shadow_receipt_id: str = "",
) -> dict[str, Any]:
    event_id = deterministic_event_id(
        tenant_id=tenant_id,
        project_id=project_id,
        plan_id=plan_id,
        event_type=event_type,
    )
    return {
        "event_id": event_id,
        "plan_id": plan_id,
        "gateway_decision_id": gateway_decision_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "source_record_id": source_record_id,
        "shadow_receipt_id": shadow_receipt_id,
        "version": GRDI_GATEWAY_EVENTS_PROTOCOL_VERSION,
        "scope": {"tenant_id": tenant_id, "project_id": project_id},
    }


def gateway_event_canonical(plan_id: str, event_type: str) -> str:
    return gateway_event_canonical_key(plan_id, event_type)
