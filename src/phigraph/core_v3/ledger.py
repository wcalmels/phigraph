from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Any

from .backends import JsonLedgerBackend, LedgerBackend
from .models import (
    ActionProposal,
    Claim,
    ClaimStatus,
    Evidence,
    Outcome,
    PolicyDecision,
    Verification,
)


class EvidenceLedger:
    """Backend-neutral ledger with scoped queries and optional HMAC evidence signatures."""

    COLLECTIONS = (
        "claims",
        "evidence",
        "verifications",
        "actions",
        "policy_decisions",
        "outcomes",
        "decision_envelopes",
        "authority_decisions",
        "execution_requests",
        "gateway_decisions",
        "shadow_execution_receipts",
    )

    def __init__(self, path: str | Path | None = None, *, backend: LedgerBackend | None = None,
                 signing_key: str | bytes | None = None):
        if backend is None:
            if path is None:
                raise ValueError("path or backend is required")
            backend = JsonLedgerBackend(path, self.COLLECTIONS)
        self.backend = backend
        self._lock = RLock()
        self.signing_key = signing_key.encode() if isinstance(signing_key, str) else signing_key

    @staticmethod
    def hash_payload(payload: Any) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def sign_hash(self, content_hash: str) -> str | None:
        if not self.signing_key:
            return None
        return hmac.new(self.signing_key, content_hash.encode(), hashlib.sha256).hexdigest()

    def _read(self) -> dict[str, list[dict[str, Any]]]:
        return self.backend.read_all()

    def _write(self, payload: dict[str, list[dict[str, Any]]]) -> None:
        self.backend.write_all(payload)

    def _rechain_payload(self, payload: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
        """Rebuild deterministic collection chains after an in-place record mutation.

        PhiGraph records are append-oriented, but verification legitimately changes the
        status/evidence references of an existing claim. Rechaining keeps the ledger
        tamper-evident after that controlled state transition.
        """
        for collection in self.COLLECTIONS:
            previous_hash = None
            rebuilt: list[dict[str, Any]] = []
            for existing in payload.get(collection, []):
                canonical = {k: v for k, v in existing.items() if k != "_chain"}
                chain_hash = self.hash_payload({
                    "previous_hash": previous_hash,
                    "collection": collection,
                    "record": canonical,
                })
                rebuilt.append({**canonical, "_chain": {
                    "previous_hash": previous_hash,
                    "hash": chain_hash,
                    "alg": "sha256",
                }})
                previous_hash = chain_hash
            payload[collection] = rebuilt
        return payload

    def repair_chain(self) -> dict[str, Any]:
        """Rebuild all collection chains for a legacy or interrupted ledger."""
        with self._lock:
            payload = self._rechain_payload(self._read())
            self._write(payload)
        return self.verify_chain()

    def _append(self, collection: str, row: dict[str, Any], *, unique_key: str) -> dict[str, Any]:
        with self._lock:
            payload = self._read()
            if any(item[unique_key] == row[unique_key] for item in payload[collection]):
                raise ValueError(f"Duplicate {unique_key}: {row[unique_key]}")
            previous_hash = payload[collection][-1].get("_chain", {}).get("hash") if payload[collection] else None
            canonical = {k: v for k, v in row.items() if k != "_chain"}
            chain_hash = self.hash_payload({"previous_hash": previous_hash, "collection": collection, "record": canonical})
            row = {**row, "_chain": {"previous_hash": previous_hash, "hash": chain_hash, "alg": "sha256"}}
            payload[collection].append(row)
            self._write(payload)
        return row

    def verify_chain(self) -> dict[str, Any]:
        payload = self._read()
        checked = 0
        heads: dict[str, str | None] = {}
        for collection in self.COLLECTIONS:
            previous_hash = None
            for row in payload[collection]:
                chain = row.get("_chain")
                if chain is None:
                    return {"valid": False, "checked": checked, "reason": "missing_chain", "collection": collection}
                if chain.get("previous_hash") != previous_hash:
                    return {"valid": False, "checked": checked, "reason": "link_mismatch", "collection": collection}
                canonical = {k: v for k, v in row.items() if k != "_chain"}
                expected = self.hash_payload({"previous_hash": previous_hash, "collection": collection, "record": canonical})
                if expected != chain.get("hash"):
                    return {"valid": False, "checked": checked, "reason": "hash_mismatch", "collection": collection}
                previous_hash = chain.get("hash")
                checked += 1
            heads[collection] = previous_hash
        return {"valid": True, "checked": checked, "heads": heads}

    @staticmethod
    def _scope_metadata(metadata: dict[str, Any], tenant_id: str, project_id: str) -> dict[str, Any]:
        return {**metadata, "tenant_id": tenant_id, "project_id": project_id}

    def register_evidence(self, evidence: Evidence, *, tenant_id: str = "default", project_id: str = "default") -> Evidence:
        if evidence.content_hash is None:
            evidence = replace(evidence, content_hash=self.hash_payload(evidence.payload))
        metadata = self._scope_metadata(evidence.metadata, tenant_id, project_id)
        signature = self.sign_hash(evidence.content_hash)
        if signature:
            metadata["signature"] = signature
            metadata["signature_alg"] = "hmac-sha256"
        evidence = replace(evidence, metadata=metadata)
        self._append("evidence", evidence.to_dict(), unique_key="evidence_id")
        return evidence

    def verify_evidence_signature(self, evidence_id: str) -> bool | None:
        row = self.get_record("evidence", evidence_id, "evidence_id")
        signature = row.get("metadata", {}).get("signature")
        if signature is None or self.signing_key is None:
            return None
        expected = self.sign_hash(row["content_hash"])
        return hmac.compare_digest(signature, expected or "")

    def register_claim(self, claim: Claim, *, tenant_id: str = "default", project_id: str = "default") -> Claim:
        claim = replace(claim, metadata=self._scope_metadata(claim.metadata, tenant_id, project_id))
        self._append("claims", claim.to_dict(), unique_key="claim_id")
        return claim

    def record_verification(self, verification: Verification, *, tenant_id: str = "default", project_id: str = "default") -> Verification:
        verification = replace(verification, metadata=self._scope_metadata(verification.metadata, tenant_id, project_id))
        with self._lock:
            payload = self._read()
            claim = next((item for item in payload["claims"] if item["claim_id"] == verification.claim_id), None)
            if claim is None:
                raise KeyError(f"Unknown claim: {verification.claim_id}")
            known_evidence = {item["evidence_id"] for item in payload["evidence"]}
            missing = set(verification.evidence_ids) - known_evidence
            if missing:
                raise KeyError(f"Unknown evidence: {sorted(missing)}")
            if any(v["verification_id"] == verification.verification_id for v in payload["verifications"]):
                raise ValueError(f"Duplicate verification_id: {verification.verification_id}")
            payload["verifications"].append(verification.to_dict())
            claim["status"] = verification.result.value
            claim["evidence_ids"] = sorted(set(claim.get("evidence_ids", [])) | set(verification.evidence_ids))
            self._write(self._rechain_payload(payload))
        return verification

    def register_action(self, action: ActionProposal, *, tenant_id: str = "default", project_id: str = "default") -> ActionProposal:
        row = action.to_dict()
        row["scope"] = {"tenant_id": tenant_id, "project_id": project_id}
        self._append("actions", row, unique_key="action_id")
        return action

    def record_policy_decision(self, decision: PolicyDecision, *, tenant_id: str = "default", project_id: str = "default") -> PolicyDecision:
        row = decision.to_dict()
        row["scope"] = {"tenant_id": tenant_id, "project_id": project_id}
        self._append("policy_decisions", row, unique_key="decision_id")
        return decision

    def record_outcome(self, outcome: Outcome, *, tenant_id: str = "default", project_id: str = "default") -> Outcome:
        row = outcome.to_dict()
        row["scope"] = {"tenant_id": tenant_id, "project_id": project_id}
        self._append("outcomes", row, unique_key="outcome_id")
        return outcome

    def register_scoped_record(
        self,
        collection: str,
        row: dict[str, Any],
        *,
        unique_key: str,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        """Append a protocol extension record with canonical tenant scope."""
        allowed = {
            "decision_envelopes",
            "authority_decisions",
            "execution_requests",
            "gateway_decisions",
            "shadow_execution_receipts",
        }
        if collection not in allowed:
            raise ValueError(f"Unsupported scoped extension collection: {collection}")
        scoped = {**row, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
        self._append(collection, scoped, unique_key=unique_key)
        return scoped

    def register_scoped_record_once(
        self,
        collection: str,
        row: dict[str, Any],
        *,
        unique_key: str,
        tenant_id: str,
        project_id: str,
    ) -> tuple[dict[str, Any], bool]:
        """Append a scoped record when absent; return the stored row and whether it was created."""
        allowed = {
            "decision_envelopes",
            "authority_decisions",
            "execution_requests",
            "gateway_decisions",
            "shadow_execution_receipts",
        }
        if collection not in allowed:
            raise ValueError(f"Unsupported scoped extension collection: {collection}")
        with self._lock:
            payload = self._read()
            for existing in payload[collection]:
                if existing[unique_key] != row[unique_key]:
                    continue
                scope = existing.get("scope", {})
                if scope.get("tenant_id") == tenant_id and scope.get("project_id") == project_id:
                    return existing, False
            scoped = {**row, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
            previous_hash = payload[collection][-1].get("_chain", {}).get("hash") if payload[collection] else None
            canonical = {k: v for k, v in scoped.items() if k != "_chain"}
            chain_hash = self.hash_payload({"previous_hash": previous_hash, "collection": collection, "record": canonical})
            stored = {**scoped, "_chain": {"previous_hash": previous_hash, "hash": chain_hash, "alg": "sha256"}}
            payload[collection].append(stored)
            self._write(payload)
            return stored, True

    def update_scoped_record(
        self,
        collection: str,
        row: dict[str, Any],
        *,
        unique_key: str,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        """Replace an existing scoped extension record and rebuild its collection chain."""
        allowed = {
            "decision_envelopes",
            "authority_decisions",
            "execution_requests",
            "gateway_decisions",
            "shadow_execution_receipts",
        }
        if collection not in allowed:
            raise ValueError(f"Unsupported scoped extension collection: {collection}")
        with self._lock:
            payload = self._read()
            for index, existing in enumerate(payload[collection]):
                if existing[unique_key] != row[unique_key]:
                    continue
                scope = existing.get("scope", {})
                if scope.get("tenant_id") != tenant_id or scope.get("project_id") != project_id:
                    raise KeyError(f"scoped_record_not_found:{row[unique_key]}")
                scoped = {**row, "scope": scope}
                payload[collection][index] = scoped
                self._write(self._rechain_payload(payload))
                return scoped
        raise KeyError(f"scoped_record_not_found:{row[unique_key]}")

    def get_record(self, collection: str, record_id: str, id_key: str) -> dict[str, Any]:
        row = next((item for item in self._read()[collection] if item[id_key] == record_id), None)
        if row is None:
            raise KeyError(f"Unknown {collection[:-1]}: {record_id}")
        return row

    def get_claim(self, claim_id: str) -> dict[str, Any]:
        return self.get_record("claims", claim_id, "claim_id")

    def query(self, collection: str, *, tenant_id: str | None = None, project_id: str | None = None,
              status: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        if collection not in self.COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection}")
        rows = self._read()[collection]
        def scoped(row: dict[str, Any]) -> bool:
            scope = row.get("scope") or row.get("metadata", {})
            return (tenant_id is None or scope.get("tenant_id") == tenant_id) and (project_id is None or scope.get("project_id") == project_id) and (status is None or row.get("status") == status)
        return [row for row in rows if scoped(row)][offset:offset + min(limit, 1000)]

    def snapshot(self, *, tenant_id: str | None = None, project_id: str | None = None) -> dict[str, Any]:
        payload = {key: self.query(key, tenant_id=tenant_id, project_id=project_id, limit=100000) for key in self.COLLECTIONS}
        payload["summary"] = {key: len(payload[key]) for key in self.COLLECTIONS}
        payload["summary"]["verified_claims"] = sum(item["status"] == ClaimStatus.VERIFIED.value for item in payload["claims"])
        return payload
