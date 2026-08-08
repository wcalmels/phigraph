from __future__ import annotations

import hashlib
import json
from typing import Any

from phigraph.version import (
    CORE_VERSION,
    HAV_ALGORITHM_ID,
    HAV_POLICY_ID,
    HAV_POLICY_VERSION,
    HAV_VERIFIER_ID,
    HAV_VERSION,
    PROTOCOL_VERSION,
)


def policy_hash() -> str:
    material = {
        "policy_id": HAV_POLICY_ID,
        "policy_version": HAV_POLICY_VERSION,
        "fail_closed": True,
        "pass_does_not_execute": True,  # nosec B105 - policy flag, not a credential
    }
    raw = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def enrich_receipt(
    receipt: dict[str, Any],
    *,
    tenant_id: str,
    project_id: str,
    issuer: str,
    verifier_subject: str,
) -> dict[str, Any]:
    enriched = dict(receipt)
    enriched["governance"] = {
        "core_version": CORE_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "hav_version": HAV_VERSION,
        "policy_id": HAV_POLICY_ID,
        "policy_version": HAV_POLICY_VERSION,
        "policy_hash": policy_hash(),
        "verifier_id": HAV_VERIFIER_ID,
        "algorithm_id": HAV_ALGORITHM_ID,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "issuer": issuer,
        "verifier_subject": verifier_subject,
        "execution_authorized": False,
        "limitations": [
            "PASS does not authorize external execution.",
            "Verification depends on authoritative source availability and evidence quality.",
            "Model consensus is not treated as authoritative truth.",
        ],
    }
    enriched["grdi_boundary"] = {
        "stage": "verification_only",
        "produces": "verification_receipt",
        "consumers": [
            "decision_envelope",
            "authority_engine",
            "execution_gateway",
            "outcome_ledger",
        ],
        "note": "GRDI Foundation is not implemented; HAV output is advisory input for later authority stages.",
    }
    return enriched
