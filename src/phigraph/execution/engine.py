from __future__ import annotations
from .models import ExecutionReceipt, RollbackReceipt
from .connectors import FakeTicketConnector, FakeMonitoringConnector
from .idempotency import IdempotencyStore
from .approvals import DualApprovalGate
from .rollback import verify_rollback_plan
from .policy import ExecutionPolicy, authorize_execution

class ControlledExecutionSandbox:
    def __init__(self, *, idempotency_store_path, policy=None):
        self.store = IdempotencyStore(idempotency_store_path)
        self.policy = policy or ExecutionPolicy()
        self.connectors = {
            "create_ticket": FakeTicketConnector(),
            "increase_monitoring": FakeMonitoringConnector(),
            "inspect": FakeMonitoringConnector(),
        }

    def execute(self, request, *, approvals, rollback_plan,
                governance_decision, readiness_grade):
        cached = self.store.get(request.idempotency_key)
        if cached:
            return ExecutionReceipt(
                request_id=request.request_id,
                status=cached["status"],
                connector=cached["connector"],
                external_reference=cached.get("external_reference"),
                executed=cached["executed"],
                dry_run=cached["dry_run"],
                idempotent_replay=True,
                details=cached.get("details",{}),
            )

        approval_result = DualApprovalGate().evaluate(approvals)
        rollback_result = verify_rollback_plan(rollback_plan)
        authorization = authorize_execution(
            request,
            policy=self.policy,
            approval_result=approval_result,
            rollback_result=rollback_result,
            governance_decision=governance_decision,
            readiness_grade=readiness_grade,
        )
        if not authorization["authorized"]:
            receipt = ExecutionReceipt(
                request.request_id,"blocked","none",None,False,
                request.dry_run,False,
                {"authorization":authorization,
                 "approval":approval_result,
                 "rollback":rollback_result},
            )
            self.store.put(request.idempotency_key, receipt.to_dict())
            return receipt

        connector = self.connectors[request.action_type]
        result = connector.execute(
            request.action_type,
            request.target,
            request.parameters,
            dry_run=True,
        )
        receipt = ExecutionReceipt(
            request.request_id,"simulated",connector.name,
            result["external_reference"],False,True,False,
            {"connector_result":result,
             "authorization":authorization,
             "approval":approval_result,
             "rollback":rollback_result},
        )
        self.store.put(request.idempotency_key, receipt.to_dict())
        return receipt

    def rollback(self, receipt):
        if not receipt.external_reference:
            return RollbackReceipt(
                receipt.request_id,"not_required",False,{}
            )
        connector = next(
            item for item in self.connectors.values()
            if item.name == receipt.connector
        )
        result = connector.rollback(
            receipt.external_reference,
            dry_run=True,
        )
        return RollbackReceipt(
            receipt.request_id,"simulated",False,result
        )
