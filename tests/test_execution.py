from phigraph.execution import *
from phigraph.execution.approvals import ApprovalRecord

def test_sandbox_idempotency_dual_approval_and_rollback(tmp_path):
    request = ExecutionRequest(
        request_id="req-1",
        case_id="case-1",
        action_type="create_ticket",
        target="truck:118",
        parameters={"priority":"high"},
        idempotency_key="idem-1",
        reversible=True,
        dry_run=True,
    )
    approvals = (
        ApprovalRecord("alice","operations",True,"t1","ok"),
        ApprovalRecord("bob","safety",True,"t2","ok"),
    )
    rollback = RollbackPlan(
        action_type="create_ticket",
        reversible=True,
        rollback_action="close_ticket",
        verification_steps=("ticket_closed",),
        timeout_seconds=60,
    )
    sandbox = ControlledExecutionSandbox(
        idempotency_store_path=tmp_path/"idem.json"
    )
    first = sandbox.execute(
        request,
        approvals=approvals,
        rollback_plan=rollback,
        governance_decision="ACCEPT",
        readiness_grade="shadow_ready",
    )
    second = sandbox.execute(
        request,
        approvals=approvals,
        rollback_plan=rollback,
        governance_decision="ACCEPT",
        readiness_grade="shadow_ready",
    )
    assert first.status == "simulated"
    assert not first.executed
    assert second.idempotent_replay
    rb = sandbox.rollback(first)
    assert not rb.rolled_back
