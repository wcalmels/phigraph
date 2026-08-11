#!/usr/bin/env python3
"""Generate frozen RC7 staging fixture payloads (GRDI 0.4.0 / Core 4.1.0-rc.7).

Run only from checkout ``44ba1cc`` with that package installed::

    pip install -e ".[postgres]"
    python scripts/generate_grdi_rc7_staging_fixture_payloads.py \\
        > scripts/data/grdi_rc7_staging_fixture_rows.json

The operational fixture loader consumes the committed JSON and refuses live GRDI model generation.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from typing import Any

from phigraph.core_v3.receipts import ReceiptSigner
from phigraph.grdi import (
    AuthorityEngine,
    DecisionEnvelope,
    ExecutionGateway,
    ExecutionRequest,
    ShadowSimulationState,
    action_hash,
)
from phigraph.version import CORE_VERSION, GRDI_VERSION

RC7_CORE_VERSION = "4.1.0-rc.7"
RC7_GRDI_VERSION = "0.4.0"
RC7_SOURCE_COMMIT = "44ba1cc08ee007183822b629f37ce00fd6a56db8"

SIGNING_KEY = "grdi-rc7-staging-fixture-key-v1"
RC7_CREATED_AT = "2026-07-29T11:59:00+00:00"
RC7_DECIDED_AT = "2026-07-29T12:00:00+00:00"
RC7_SIMULATED_AT = "2026-07-29T12:01:00+00:00"
MARKER = "grdi-rc7-staging-fixture"
TENANT_A, TENANT_B = "tenant-a", "tenant-b"
PROJECT_A, PROJECT_B = "project-a", "project-b"

PLAN_SPECS = (
    {
        "key": "authorized",
        "tenant_id": TENANT_A,
        "project_id": PROJECT_A,
        "suffix": "001",
        "simulated": False,
        "with_receipt": False,
    },
    {
        "key": "simulated_with_receipt",
        "tenant_id": TENANT_A,
        "project_id": PROJECT_B,
        "suffix": "002",
        "simulated": True,
        "with_receipt": True,
    },
    {
        "key": "simulated_without_receipt",
        "tenant_id": TENANT_B,
        "project_id": PROJECT_A,
        "suffix": "003",
        "simulated": True,
        "with_receipt": False,
    },
    {
        "key": "simulated_with_receipt_tenant_b",
        "tenant_id": TENANT_B,
        "project_id": PROJECT_B,
        "suffix": "004",
        "simulated": True,
        "with_receipt": True,
    },
)

UNIQUE_KEYS = {
    "decision_envelopes": "envelope_id",
    "authority_decisions": "authority_decision_id",
    "execution_requests": "plan_id",
    "gateway_decisions": "gateway_decision_id",
    "shadow_execution_receipts": "receipt_id",
}


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def require_rc7_runtime() -> None:
    if CORE_VERSION != RC7_CORE_VERSION or GRDI_VERSION != RC7_GRDI_VERSION:
        _fail(
            f"refusing payload generation: installed phigraph is "
            f"core={CORE_VERSION} grdi={GRDI_VERSION}; "
            f"required core={RC7_CORE_VERSION} grdi={RC7_GRDI_VERSION}. "
            f"Use worktree at {RC7_SOURCE_COMMIT}."
        )


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def receipt(signer: ReceiptSigner, tenant_id: str, project_id: str) -> dict[str, Any]:
    return signer.sign(
        {
            "receipt_id": f"hav_rc7_{tenant_id}_{project_id}",
            "verdict": "PASS",
            "output_hash": "rc7staging0001",
            "governance": {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "execution_authorized": False,
            },
        }
    )


def row(collection: str, payload: dict[str, Any], tenant_id: str, project_id: str) -> dict[str, Any]:
    scoped = {**payload, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
    unique_key = UNIQUE_KEYS[collection]
    record_id = str(scoped[unique_key])
    return {
        "collection": collection,
        "record_id": record_id,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "payload": scoped,
        "payload_hash": payload_hash(scoped),
    }


def add_plan(
    rows: list[dict[str, Any]],
    signer: ReceiptSigner,
    *,
    tenant_id: str,
    project_id: str,
    suffix: str,
    simulated: bool,
    with_receipt: bool,
) -> str:
    envelope_id = f"de_rc7_staging_{suffix}"
    authority_decision_id = f"ad_rc7_staging_{suffix}"
    plan_id = f"ep_rc7_staging_{suffix}"
    gateway_decision_id = f"gd_rc7_staging_{suffix}"
    receipt_id = f"sr_rc7_staging_{suffix}"

    env = DecisionEnvelope(
        envelope_id=envelope_id,
        tenant_id=tenant_id,
        project_id=project_id,
        domain="software",
        decision_type="promote_release",
        subject="phigraph@staging-rc7",
        proposed_by="release-agent-staging",
        proposed_action={"type": "promote", "target": "staging"},
        hav_receipt=receipt(signer, tenant_id, project_id),
        required_authority="verifier",
        risk_level="medium",
        created_at=RC7_CREATED_AT,
    )
    auth = AuthorityEngine(signer).evaluate(
        env,
        authority_subject="human-verifier-staging",
        authority_role="verifier",
    )
    auth = replace(
        auth,
        authority_decision_id=authority_decision_id,
        decided_at=RC7_CREATED_AT,
    )
    requested_action = env.proposed_action
    req = ExecutionRequest(
        plan_id=plan_id,
        envelope_id=envelope_id,
        authority_decision_id=authority_decision_id,
        tenant_id=tenant_id,
        project_id=project_id,
        requested_by=MARKER,
        requested_action=requested_action,
        action_hash=action_hash(requested_action),
        expected_effects=("staging promotion recorded",),
        rollback_strategy={"type": "revert_release", "target": "previous"},
        created_at=RC7_DECIDED_AT,
    )
    gw = ExecutionGateway(signer).evaluate(
        envelope=env,
        authority=auth,
        request=req,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    gw = replace(
        gw,
        gateway_decision_id=gateway_decision_id,
        decided_at=RC7_DECIDED_AT,
        simulation_state=(
            ShadowSimulationState.SIMULATED if simulated else ShadowSimulationState.NOT_SIMULATED
        ),
    )
    gw_row = gw.to_dict()

    for collection, payload in (
        ("decision_envelopes", env.to_dict()),
        ("authority_decisions", auth.to_dict()),
        ("execution_requests", req.to_dict()),
        ("gateway_decisions", gw_row),
    ):
        rows.append(row(collection, payload, tenant_id, project_id))

    if simulated and with_receipt:
        rcpt = ExecutionGateway(signer).simulate(
            envelope=env,
            authority=auth,
            request=req,
            gateway=gw,
        )
        rcpt = replace(rcpt, receipt_id=receipt_id)
        rr = rcpt.to_dict()
        rr["simulated_at"] = RC7_SIMULATED_AT
        rows.append(row("shadow_execution_receipts", rr, tenant_id, project_id))
    return plan_id


def main() -> int:
    require_rc7_runtime()
    signer = ReceiptSigner.create(SIGNING_KEY)
    rows: list[dict[str, Any]] = []
    plans: dict[str, str] = {}
    for spec in PLAN_SPECS:
        plans[spec["key"]] = add_plan(
            rows,
            signer,
            tenant_id=spec["tenant_id"],
            project_id=spec["project_id"],
            suffix=spec["suffix"],
            simulated=spec["simulated"],
            with_receipt=spec["with_receipt"],
        )
    manifest = {
        "fixture": "grdi-rc7-staging",
        "rc7_source_commit": RC7_SOURCE_COMMIT,
        "core_version": RC7_CORE_VERSION,
        "grdi_version": RC7_GRDI_VERSION,
        "signing_key_id": SIGNING_KEY,
        "fixture_marker": MARKER,
        "expected_row_count": len(rows),
        "expected_plan_count": len(plans),
        "plans": plans,
        "rows": rows,
    }
    json.dump(manifest, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
