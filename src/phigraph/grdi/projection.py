"""Derived gateway state from immutable decision + append-only events."""

from __future__ import annotations

from typing import Any

from phigraph.grdi.models import ExecutionState, GatewayDecision, ShadowSimulationState


def project_gateway_state(
    signed_gateway: GatewayDecision,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    simulation_state = ShadowSimulationState.NOT_SIMULATED
    for event in sorted(events, key=lambda row: (row.get("occurred_at", ""), row.get("event_id", ""))):
        if event.get("event_type") == "SIMULATION_RECORDED":
            simulation_state = ShadowSimulationState.SIMULATED
    return {
        "simulation_state": simulation_state.value,
        "execution_state": signed_gateway.execution_state.value,
        "eligibility": signed_gateway.eligibility.value,
    }


def build_plan_projection(
    *,
    request: dict[str, Any],
    signed_gateway: GatewayDecision,
    authority: dict[str, Any],
    events: list[dict[str, Any]],
    shadow_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_state = project_gateway_state(signed_gateway, events)
    return {
        "plan_id": request["plan_id"],
        "execution_request": request,
        "signed_gateway_decision": signed_gateway.to_dict(),
        "current_gateway_state": current_state,
        "gateway_events": events,
        "flow_state": {
            "verification": authority.get("verification_state"),
            "authorization": authority.get("authorization_state"),
            "gateway_eligibility": signed_gateway.eligibility.value,
            "simulation": current_state["simulation_state"],
            "execution": ExecutionState.NOT_EXECUTED.value,
        },
        "gateway_decision": signed_gateway.to_dict(),
        "shadow_receipt": shadow_receipt,
    }
