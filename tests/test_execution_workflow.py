import pandas as pd
from phigraph.execution_workflow import *

def test_execution_sandbox_workflow(tmp_path):
    tables = {
        "fuel":pd.DataFrame({
            "camion":[f"KLG-{100+i%8}" for i in range(40)],
            "surtidor":[f"S{i%3}" for i in range(40)],
            "litros":[400+i for i in range(40)],
        }),
        "trips":pd.DataFrame({
            "equipo":[str(100+i%8) for i in range(40)],
            "ruta":[f"R{i%4}" for i in range(40)],
            "toneladas":[100+i%10 for i in range(40)],
        }),
    }
    report = run_execution_sandbox_workflow(
        tables,
        ExecutionSandboxWorkflowConfig(
            n_null_controls=5,
            human_approval=True,
            rollback_available=True,
            operations_score=.9,
            decision_audit_path=str(tmp_path/"audit.json"),
            shadow_store_path=str(tmp_path/"shadow.json"),
            advisory_queue_path=str(tmp_path/"queue.json"),
            idempotency_store_path=str(tmp_path/"idem.json"),
            advisory_action={
                "action_type":"create_ticket",
                "target":"truck:118",
                "reversible":True,
                "estimated_impact":.5,
                "estimated_risk":.1,
                "parameters":{},
            },
            execution_request={
                "request_id":"req-1",
                "case_id":"case-1",
                "action_type":"create_ticket",
                "target":"truck:118",
                "parameters":{"priority":"high"},
                "idempotency_key":"idem-1",
                "reversible":True,
                "dry_run":True,
            },
            rollback_plan={
                "action_type":"create_ticket",
                "reversible":True,
                "rollback_action":"close_ticket",
                "verification_steps":("ticket_closed",),
                "timeout_seconds":60,
            },
            execution_approvals=(
                {
                    "approver":"alice",
                    "role":"operations",
                    "approved":True,
                    "approved_at":"2026-07-23T10:00:00+00:00",
                    "rationale":"approved",
                },
                {
                    "approver":"bob",
                    "role":"safety",
                    "approved":True,
                    "approved_at":"2026-07-23T10:05:00+00:00",
                    "rationale":"approved",
                },
            ),
        ),
        reference_tables=tables,
    )
    assert report["results"][-1]["agent"] == "execution_sandbox"
    assert report["artifacts"]["execution_sandbox"]["real_system_modified"] is False
