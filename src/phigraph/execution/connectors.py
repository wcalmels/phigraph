from __future__ import annotations
from abc import ABC, abstractmethod
import uuid

class SandboxConnector(ABC):
    name = "sandbox"
    @abstractmethod
    def execute(self, action_type, target, parameters, *, dry_run=True): ...
    @abstractmethod
    def rollback(self, external_reference, *, dry_run=True): ...

class FakeTicketConnector(SandboxConnector):
    name = "fake_ticket"
    def execute(self, action_type, target, parameters, *, dry_run=True):
        if action_type != "create_ticket":
            raise ValueError("FakeTicketConnector only supports create_ticket")
        ref = f"SIM-TKT-{uuid.uuid4().hex[:8]}"
        return {"external_reference": ref, "status": "simulated",
                "target": target, "parameters": parameters, "dry_run": dry_run}
    def rollback(self, external_reference, *, dry_run=True):
        return {"external_reference": external_reference,
                "status": "simulated_closed", "dry_run": dry_run}

class FakeMonitoringConnector(SandboxConnector):
    name = "fake_monitoring"
    def execute(self, action_type, target, parameters, *, dry_run=True):
        if action_type not in {"increase_monitoring","inspect"}:
            raise ValueError("Unsupported monitoring action")
        ref = f"SIM-MON-{uuid.uuid4().hex[:8]}"
        return {"external_reference": ref, "status": "simulated",
                "target": target, "parameters": parameters, "dry_run": dry_run}
    def rollback(self, external_reference, *, dry_run=True):
        return {"external_reference": external_reference,
                "status": "simulated_restored", "dry_run": dry_run}
