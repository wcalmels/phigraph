from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import pytest
from test_grdi_foundation import _envelope

from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi.service import GRDIService

pytest.importorskip("psycopg")


def _authorized_plan(tmp_path: Path, *, dsn: str) -> tuple[str, str, str]:
    core = CoreV3Service(backend="postgres", postgres_dsn=dsn, receipt_signing_key="secret")
    grdi = GRDIService(core)
    envelope = grdi.register_envelope(_envelope(core.receipt_signer))
    decision = grdi.authorize(
        envelope.envelope_id,
        tenant_id="tenant-a",
        project_id="project-a",
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    plan = grdi.create_execution_plan(
        envelope_id=envelope.envelope_id,
        authority_decision_id=decision.authority_decision_id,
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
        requested_action=envelope.proposed_action,
    )
    return plan["plan_id"], "tenant-a", "project-a"


def _simulate_worker(dsn: str, plan_id: str, tenant_id: str, project_id: str, out: mp.Queue) -> None:
    try:
        core = CoreV3Service(backend="postgres", postgres_dsn=dsn, receipt_signing_key="secret")
        grdi = GRDIService(core)
        result = grdi.simulate_execution_plan(plan_id, tenant_id=tenant_id, project_id=project_id)
        out.put(("ok", result["shadow_receipt"]["receipt_id"]))
    except Exception as exc:
        out.put(("err", str(exc)))


def test_postgres_simulate_eight_workers_one_receipt(postgres_dsn, tmp_path):
    plan_id, tenant_id, project_id = _authorized_plan(tmp_path, dsn=postgres_dsn)
    out: mp.Queue = mp.Queue()
    workers = [
        mp.Process(target=_simulate_worker, args=(postgres_dsn, plan_id, tenant_id, project_id, out))
        for _ in range(8)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=60)
    results = [out.get(timeout=10) for _ in workers]
    assert all(status == "ok" for status, _ in results)
    receipt_ids = {receipt_id for _, receipt_id in results}
    assert len(receipt_ids) == 1

    core = CoreV3Service(backend="postgres", postgres_dsn=postgres_dsn, receipt_signing_key="secret")
    grdi = GRDIService(core)
    events = grdi._list_gateway_events(plan_id, tenant_id=tenant_id, project_id=project_id)
    simulation_events = [event for event in events if event["event_type"] == "SIMULATION_RECORDED"]
    assert len(simulation_events) == 1
    gateway = grdi._scoped_get(
        "gateway_decisions",
        canonical_key=plan_id,
        tenant_id=tenant_id,
        project_id=project_id,
        error="missing",
    )
    signed = grdi._gateway_from_row(gateway)
    assert signed.simulation_state.value == "NOT_SIMULATED"
