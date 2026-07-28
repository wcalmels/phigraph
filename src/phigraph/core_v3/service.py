from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .adapters import AgentAdapter
from .integrations import LegacyBridge, LegacyIntegrationPaths
from .backends import PostgreSQLLedgerBackend, SQLiteLedgerBackend
from .idempotency import IdempotencyStore
from .ledger import EvidenceLedger
from .models import ActionProposal, RuntimeMode
from .policy import PolicyEngine
from .runtime import PhiGraphCoreRuntime, RuntimeReport, Verifier
from .sandbox import CoreV3SandboxBridge
from .telemetry import TraceRecorder
from .receipts import ReceiptSigner


class CoreV3Service:
    """Application service composing ledger, policy, runtime and legacy mirrors."""

    def __init__(
        self,
        *,
        data_dir: str | Path,
        policy_engine: PolicyEngine | None = None,
        verifiers: dict[str, Verifier] | None = None,
        backend: str = "json",
        signing_key: str | None = None,
        postgres_dsn: str | None = None,
        receipt_signing_key: str | None = None,
        sandbox_isolated: bool = False,
        otlp_endpoint: str | None = None,
    ):
        root = Path(data_dir)
        root.mkdir(parents=True, exist_ok=True)
        if backend == "sqlite":
            ledger_backend = SQLiteLedgerBackend(root / "core_v3_ledger.sqlite3", EvidenceLedger.COLLECTIONS)
        elif backend in {"postgres", "postgresql"}:
            if not postgres_dsn:
                raise ValueError("postgres_dsn is required for PostgreSQL backend")
            ledger_backend = PostgreSQLLedgerBackend(postgres_dsn, EvidenceLedger.COLLECTIONS)
        elif backend == "json":
            ledger_backend = None
        else:
            raise ValueError(f"Unsupported ledger backend: {backend}")
        self.ledger = EvidenceLedger(root / "core_v3_ledger.json" if ledger_backend is None else None, backend=ledger_backend, signing_key=signing_key)
        self.idempotency = IdempotencyStore(root / "core_v3_idempotency.json")
        self.telemetry = TraceRecorder(otlp_endpoint=otlp_endpoint)
        receipt_signer = ReceiptSigner.create(receipt_signing_key) if receipt_signing_key else None
        self.sandbox = CoreV3SandboxBridge(root, signer=receipt_signer, isolated=sandbox_isolated)
        self.receipt_signer = receipt_signer
        self.bridge = LegacyBridge(
            ledger=self.ledger,
            paths=LegacyIntegrationPaths(
                audit_path=root / "core_v3_decision_audit.json",
                shadow_path=root / "core_v3_shadow_runs.json",
            ),
        )
        self.runtime = PhiGraphCoreRuntime(
            ledger=self.ledger,
            policy_engine=policy_engine,
            verifiers=verifiers,
            event_sink=self._mirror_event,
        )

    def _mirror_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "policy_decision":
            self.bridge.mirror_policy_decision(
                payload["decision"],
                case_id=payload["action"].target,
                dossier={"action": payload["action"].to_dict(), "decision": payload["decision"].to_dict()},
            )
        elif event_type == "outcome" and not payload["outcome"].executed:
            self.bridge.mirror_shadow_outcome(
                action=payload["action"],
                outcome=payload["outcome"],
            )

    def run(
        self,
        *,
        adapter: AgentAdapter,
        request: dict[str, Any],
        context: dict[str, Any] | None = None,
        mode: RuntimeMode = RuntimeMode.SHADOW,
        approvals: tuple[str, ...] = (),
        executor: Callable[[ActionProposal], dict[str, Any]] | None = None,
        tenant_id: str = "default", project_id: str = "default",
    ) -> RuntimeReport:
        with self.telemetry.span("core.runtime.run", mode=mode.value, tenant_id=tenant_id, project_id=project_id):
            return self.runtime.run(
            adapter=adapter,
            request=request,
            context=context,
            mode=mode,
            approvals=approvals,
            executor=executor, tenant_id=tenant_id, project_id=project_id,
            )
