from __future__ import annotations

import pytest

from phigraph.core_v3.backends import SQLiteLedgerBackend
from phigraph.core_v3.ledger import EvidenceLedger


@pytest.fixture
def tenant_id() -> str:
    return "tenant-a"


@pytest.fixture
def project_id() -> str:
    return "project-a"


@pytest.fixture
def receipt_record() -> dict:
    return {
        "receipt_id": "rcpt_contract_1",
        "plan_id": "plan_contract_1",
        "simulation_state": "SIMULATED",
        "execution_state": "NOT_EXECUTED",
    }


@pytest.fixture
def json_ledger(tmp_path):
    def factory(*, transactional_mode: str = "single_process") -> EvidenceLedger:
        return EvidenceLedger(tmp_path / "ledger.json", transactional_mode=transactional_mode)
    return factory


@pytest.fixture
def sqlite_ledger(tmp_path):
    def factory() -> EvidenceLedger:
        backend = SQLiteLedgerBackend(tmp_path / "ledger.db", EvidenceLedger.COLLECTIONS)
        return EvidenceLedger(backend=backend)
    return factory
