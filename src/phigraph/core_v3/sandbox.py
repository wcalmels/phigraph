from __future__ import annotations

import multiprocessing as mp
from pathlib import Path
from typing import Any

from phigraph.execution import ControlledExecutionSandbox, ExecutionRequest, RollbackPlan
from phigraph.execution.approvals import make_approval

from .models import ActionProposal
from .receipts import ReceiptSigner


def _isolated_execute(queue: Any, data_dir: str, action_row: dict[str, Any], approvals: tuple[str, ...], governance_decision: str, readiness_grade: str) -> None:
    try:
        bridge = CoreV3SandboxBridge(data_dir, isolated=False)
        action = ActionProposal(**{k: v for k, v in action_row.items() if k in ActionProposal.__dataclass_fields__})
        queue.put({"ok": True, "receipt": bridge.execute(action, approvals=approvals, governance_decision=governance_decision, readiness_grade=readiness_grade)})
    except Exception as exc:
        queue.put({"ok": False, "error": f"{type(exc).__name__}:{exc}"})


class CoreV3SandboxBridge:
    """Maps canonical actions to the dry-run sandbox, optionally in an isolated child process."""

    def __init__(self, data_dir: str | Path, *, signer: ReceiptSigner | None = None, isolated: bool = False, timeout_seconds: int = 15):
        self.data_dir = Path(data_dir)
        self.sandbox = ControlledExecutionSandbox(idempotency_store_path=self.data_dir / "core_v3_execution_idempotency.json")
        self.signer = signer
        self.isolated = isolated
        self.timeout_seconds = timeout_seconds

    def _execute_local(self, action: ActionProposal, *, approvals: tuple[str, ...], governance_decision: str, readiness_grade: str) -> dict[str, Any]:
        request = ExecutionRequest(
            request_id=action.action_id,
            case_id=action.target,
            action_type=action.action_type,
            target=action.target,
            parameters=action.parameters,
            idempotency_key=action.action_id,
            reversible=action.reversible,
            dry_run=True,
        )
        roles = ("operations", "safety")
        approval_rows = tuple(make_approval(value, roles[i] if i < 2 else "operations", True, "core-v3") for i, value in enumerate(approvals))
        rollback = RollbackPlan(
            action_type=action.action_type,
            reversible=bool(action.reversible),
            rollback_action=f"rollback:{action.action_type}",
            verification_steps=("verify previous state restored",),
            timeout_seconds=60,
        )
        receipt = self.sandbox.execute(
            request,
            approvals=approval_rows,
            rollback_plan=rollback,
            governance_decision=governance_decision,
            readiness_grade=readiness_grade,
        ).to_dict()
        receipt["isolation"] = "process" if self.isolated else "in_process"
        return self.signer.sign(receipt) if self.signer else receipt

    def execute(self, action: ActionProposal, *, approvals: tuple[str, ...] = (), governance_decision: str = "APPROVED", readiness_grade: str = "pilot_ready") -> dict[str, Any]:
        if not self.isolated:
            return self._execute_local(action, approvals=approvals, governance_decision=governance_decision, readiness_grade=readiness_grade)
        context = mp.get_context("spawn")
        queue = context.Queue()
        process = context.Process(target=_isolated_execute, args=(queue, str(self.data_dir), action.to_dict(), approvals, governance_decision, readiness_grade))
        process.start()
        process.join(self.timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join()
            raise TimeoutError("sandbox_execution_timeout")
        if queue.empty():
            raise RuntimeError("sandbox_worker_failed_without_receipt")
        result = queue.get()
        if not result["ok"]:
            raise RuntimeError(result["error"])
        receipt = result["receipt"]
        receipt["isolation"] = "process"
        return self.signer.sign(receipt) if self.signer else receipt
