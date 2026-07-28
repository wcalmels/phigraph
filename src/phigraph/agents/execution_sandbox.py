from phigraph.execution import (
    ExecutionRequest, RollbackPlan, ControlledExecutionSandbox,
)
from phigraph.execution.approvals import ApprovalRecord
from .base import AgentContext, AgentResult

class ExecutionSandboxAgent:
    name = "execution_sandbox"

    def run(self, context):
        advisory = context.artifacts.get("advisory_control", {})
        governance = context.artifacts.get("governance", {})
        readiness = context.artifacts.get("production_readiness", {})
        request_data = context.payload.get("execution_request")
        rollback_data = context.payload.get("rollback_plan")
        approval_rows = context.payload.get("execution_approvals", [])

        if not request_data or not rollback_data:
            return AgentResult(
                self.name, "blocked",
                "Execution request and rollback plan are required.", {}
            )

        request = ExecutionRequest(**request_data)
        rollback = RollbackPlan(**rollback_data)
        approvals = tuple(ApprovalRecord(**row) for row in approval_rows)

        sandbox = ControlledExecutionSandbox(
            idempotency_store_path=context.payload.get(
                "idempotency_store_path",
                "data/execution_idempotency.json",
            )
        )
        receipt = sandbox.execute(
            request,
            approvals=approvals,
            rollback_plan=rollback,
            governance_decision=governance.get(
                "consensus", {}
            ).get("decision", "INSUFFICIENT_EVIDENCE"),
            readiness_grade=readiness.get(
                "grade", "laboratory_only"
            ),
        )
        rollback_receipt = None
        if context.payload.get("simulate_rollback", True):
            rollback_receipt = sandbox.rollback(receipt).to_dict()

        output = {
            "receipt": receipt.to_dict(),
            "rollback_receipt": rollback_receipt,
            "real_system_modified": False,
        }
        context.artifacts["execution_sandbox"] = output
        context.record(
            self.name,
            "simulate_controlled_execution",
            output,
        )
        return AgentResult(
            self.name,
            "ok" if receipt.status == "simulated" else "warning",
            receipt.status,
            output,
        )
