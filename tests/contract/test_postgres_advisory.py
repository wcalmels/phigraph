from __future__ import annotations

import hashlib

import pytest

from phigraph.core_v3.postgres_advisory import lock_ref_advisory_keys, lock_ref_encoding
from phigraph.core_v3.transactions import LockKind, LockRef

pytest.importorskip("psycopg")


ADVISORY_VECTORS = [
    (
        LockRef("tenant-a", "project-a", "shadow_execution_receipts", LockKind.CHAIN),
        "phigraph:scoped-lock:v1\x1ftenant-a\x1fproject-a\x1fshadow_execution_receipts\x1fchain\x1f",
        (-1677643681, 1306483324),
    ),
    (
        LockRef(
            "tenant-a",
            "project-a",
            "shadow_execution_receipts",
            LockKind.CANONICAL,
            "plan_1",
        ),
        "phigraph:scoped-lock:v1\x1ftenant-a\x1fproject-a\x1fshadow_execution_receipts\x1fcanonical\x1fplan_1",
        (715018128, -2130258531),
    ),
    (
        LockRef("tenant-b", "project-b", "actions", LockKind.CANONICAL, "act_1"),
        "phigraph:scoped-lock:v1\x1ftenant-b\x1fproject-b\x1faction\x1fcanonical\x1fact_1",
        None,
    ),
]


def _expected_keys(encoding: str) -> tuple[int, int]:
    digest = hashlib.sha256(encoding.encode("utf-8")).digest()
    key1 = int.from_bytes(digest[0:4], "big", signed=True)
    key2 = int.from_bytes(digest[4:8], "big", signed=True)
    return key1, key2


@pytest.mark.parametrize("ref,encoding,keys", ADVISORY_VECTORS[:2])
def test_lock_ref_advisory_vectors(ref: LockRef, encoding: str, keys: tuple[int, int]) -> None:
    assert lock_ref_encoding(ref) == encoding
    assert lock_ref_advisory_keys(ref) == keys
    assert lock_ref_advisory_keys(ref) == _expected_keys(encoding)


def test_lock_ref_advisory_deterministic_across_calls() -> None:
    ref = LockRef("tenant-a", "project-a", "shadow_execution_receipts", LockKind.CHAIN)
    first = lock_ref_advisory_keys(ref)
    second = lock_ref_advisory_keys(ref)
    assert first == second
    assert all(isinstance(value, int) for value in first)
    assert all(-(2**31) <= value < 2**31 for value in first)
