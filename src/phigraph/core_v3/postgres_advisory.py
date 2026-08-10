"""Deterministic PostgreSQL advisory lock keys for scoped transactional writes (ADR-021)."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from .transactions import LockKind, LockRef, normalize_lock_refs

# Namespace prefix prevents accidental collision with unrelated advisory users.
_LOCK_NAMESPACE = "phigraph:scoped-lock:v1"


def lock_ref_encoding(ref: LockRef) -> str:
    """Canonical string encoded into the SHA-256 digest."""
    canonical_key = ref.canonical_key if ref.kind == LockKind.CANONICAL else ""
    return "\x1f".join(
        [
            _LOCK_NAMESPACE,
            ref.tenant_id,
            ref.project_id,
            ref.collection,
            ref.kind.value,
            canonical_key,
        ]
    )


def lock_ref_advisory_keys(ref: LockRef) -> tuple[int, int]:
    """Map a LockRef to ``pg_advisory_xact_lock(int, int)`` key pair.

    Encoding:
    1. Build ``lock_ref_encoding(ref)`` (UTF-8).
    2. ``digest = SHA-256(encoding)`` (32 bytes).
    3. ``key1 = int.from_bytes(digest[0:4], 'big', signed=True)``
    4. ``key2 = int.from_bytes(digest[4:8], 'big', signed=True)``

    Python ``hash()`` is never used. Keys are stable across processes and machines.
    """
    digest = hashlib.sha256(lock_ref_encoding(ref).encode("utf-8")).digest()
    key1 = int.from_bytes(digest[0:4], "big", signed=True)
    key2 = int.from_bytes(digest[4:8], "big", signed=True)
    return key1, key2


def acquire_advisory_locks(conn: Any, lock_refs: Iterable[LockRef]) -> None:
    """Acquire transaction-scoped advisory locks in global LockRef order."""
    for ref in normalize_lock_refs(tuple(lock_refs)):
        key1, key2 = lock_ref_advisory_keys(ref)
        conn.execute("SELECT pg_advisory_xact_lock(%s, %s)", (key1, key2))


def implicit_write_lock_refs(
    *,
    tenant_id: str,
    project_id: str,
    collection: str,
    canonical_key: str,
    chain_linked: bool,
) -> tuple[LockRef, ...]:
    """Locks required for a standalone scoped write outside ``run_scoped_transaction``."""
    refs: list[LockRef] = []
    if chain_linked:
        refs.append(LockRef(tenant_id, project_id, collection, LockKind.CHAIN))
    refs.append(
        LockRef(tenant_id, project_id, collection, LockKind.CANONICAL, canonical_key)
    )
    return normalize_lock_refs(tuple(refs))
