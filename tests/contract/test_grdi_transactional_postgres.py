from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import pytest
from test_grdi_foundation import _envelope
from test_grdi_outcome_ledger import _matched_assessment

from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi.service import GRDIService

pytest.importorskip("psycopg")


def _authorized_plan(tmp_path: Path, *, dsn: str) -> tuple[str, str, str, str]:
    core = CoreV3Service(data_dir=tmp_path, backend="postgres", postgres_dsn=dsn, receipt_signing_key="secret")
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
    return str(tmp_path), plan["plan_id"], "tenant-a", "project-a"


def _authorized_simulated_plan(tmp_path: Path, *, dsn: str) -> tuple[GRDIService, str, str, str]:
    core = CoreV3Service(data_dir=tmp_path, backend="postgres", postgres_dsn=dsn, receipt_signing_key="secret")
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
    grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    return grdi, plan["plan_id"], "tenant-a", "project-a"


def _simulate_worker(data_dir: str, dsn: str, plan_id: str, tenant_id: str, project_id: str, out: mp.Queue) -> None:
    try:
        core = CoreV3Service(data_dir=data_dir, backend="postgres", postgres_dsn=dsn, receipt_signing_key="secret")
        grdi = GRDIService(core)
        result = grdi.simulate_execution_plan(plan_id, tenant_id=tenant_id, project_id=project_id)
        out.put(("ok", result["shadow_receipt"]["receipt_id"]))
    except Exception as exc:
        out.put(("err", str(exc)))


def _outcome_worker(data_dir: str, dsn: str, plan_id: str, tenant_id: str, project_id: str, out: mp.Queue) -> None:
    try:
        core = CoreV3Service(data_dir=data_dir, backend="postgres", postgres_dsn=dsn, receipt_signing_key="secret")
        grdi = GRDIService(core)
        result = grdi.record_shadow_outcome(
            plan_id,
            tenant_id=tenant_id,
            project_id=project_id,
            recorded_by="human-verifier",
            effect_assessments=(_matched_assessment("staging promotion recorded"),),
        )
        out.put(("ok", result["outcome_id"]))
    except Exception as exc:
        out.put(("err", str(exc)))


def _replay_worker(data_dir: str, dsn: str, plan_id: str, tenant_id: str, project_id: str, out: mp.Queue) -> None:
    try:
        core = CoreV3Service(data_dir=data_dir, backend="postgres", postgres_dsn=dsn, receipt_signing_key="secret")
        grdi = GRDIService(core)
        result = grdi.create_replay_report(
            plan_id,
            tenant_id=tenant_id,
            project_id=project_id,
            requested_by="auditor-a",
        )
        out.put(("ok", result["replay_id"]))
    except Exception as exc:
        out.put(("err", str(exc)))


def _comparison_worker(
    data_dir: str,
    dsn: str,
    baseline_id: str,
    candidate_id: str,
    tenant_id: str,
    project_id: str,
    out: mp.Queue,
) -> None:
    try:
        core = CoreV3Service(data_dir=data_dir, backend="postgres", postgres_dsn=dsn, receipt_signing_key="secret")
        grdi = GRDIService(core)
        result = grdi.compare_replays(
            baseline_id,
            candidate_id,
            tenant_id=tenant_id,
            project_id=project_id,
            requested_by="auditor-a",
        )
        out.put(("ok", result["comparison_id"]))
    except Exception as exc:
        out.put(("err", str(exc)))


def test_postgres_simulate_eight_workers_one_receipt(postgres_dsn, tmp_path):
    data_dir, plan_id, tenant_id, project_id = _authorized_plan(tmp_path, dsn=postgres_dsn)
    out: mp.Queue = mp.Queue()
    workers = [
        mp.Process(target=_simulate_worker, args=(data_dir, postgres_dsn, plan_id, tenant_id, project_id, out))
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

    core = CoreV3Service(data_dir=tmp_path, backend="postgres", postgres_dsn=postgres_dsn, receipt_signing_key="secret")
    grdi = GRDIService(core)
    events = grdi._list_gateway_events(plan_id, tenant_id=tenant_id, project_id=project_id)
    simulation_events = [event for event in events if event["event_type"] == "SIMULATION_RECORDED"]
    assert len(simulation_events) == 1


def test_postgres_outcome_eight_workers_one_record(postgres_dsn, tmp_path):
    grdi, plan_id, tenant_id, project_id = _authorized_simulated_plan(tmp_path, dsn=postgres_dsn)
    _ = grdi
    data_dir = str(tmp_path)
    out: mp.Queue = mp.Queue()
    workers = [
        mp.Process(target=_outcome_worker, args=(data_dir, postgres_dsn, plan_id, tenant_id, project_id, out))
        for _ in range(8)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=60)
    results = [out.get(timeout=10) for _ in workers]
    assert all(status == "ok" for status, _ in results)
    outcome_ids = {outcome_id for _, outcome_id in results}
    assert len(outcome_ids) == 1


def test_postgres_replay_eight_workers_one_report(postgres_dsn, tmp_path):
    grdi, plan_id, tenant_id, project_id = _authorized_simulated_plan(tmp_path, dsn=postgres_dsn)
    grdi.record_shadow_outcome(
        plan_id,
        tenant_id=tenant_id,
        project_id=project_id,
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("staging promotion recorded"),),
    )
    data_dir = str(tmp_path)
    out: mp.Queue = mp.Queue()
    workers = [
        mp.Process(target=_replay_worker, args=(data_dir, postgres_dsn, plan_id, tenant_id, project_id, out))
        for _ in range(8)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=60)
    results = [out.get(timeout=10) for _ in workers]
    assert all(status == "ok" for status, _ in results)
    replay_ids = {replay_id for _, replay_id in results}
    assert len(replay_ids) == 1


def test_postgres_comparison_eight_workers_one_row(postgres_dsn, tmp_path):
    grdi, plan_id, tenant_id, project_id = _authorized_simulated_plan(tmp_path, dsn=postgres_dsn)
    grdi.record_shadow_outcome(
        plan_id,
        tenant_id=tenant_id,
        project_id=project_id,
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("staging promotion recorded"),),
    )
    baseline = grdi.create_replay_report(
        plan_id,
        tenant_id=tenant_id,
        project_id=project_id,
        requested_by="auditor-a",
    )
    candidate = grdi.create_replay_report(
        plan_id,
        tenant_id=tenant_id,
        project_id=project_id,
        requested_by="auditor-b",
    )
    data_dir = str(tmp_path)
    out: mp.Queue = mp.Queue()
    workers = [
        mp.Process(
            target=_comparison_worker,
            args=(data_dir, postgres_dsn, baseline["replay_id"], candidate["replay_id"], tenant_id, project_id, out),
        )
        for _ in range(8)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=60)
    results = [out.get(timeout=10) for _ in workers]
    assert all(status == "ok" for status, _ in results)
    comparison_ids = {comparison_id for _, comparison_id in results}
    assert len(comparison_ids) == 1
