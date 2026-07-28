from __future__ import annotations
from dataclasses import dataclass

from phigraph.governance_workflow import run_governed_production_workflow
from .store import ShadowDeploymentStore

@dataclass
class ShadowDeploymentRunner:
    store: ShadowDeploymentStore

    def run(self, tables, config, *, reference_tables=None, calibration_labels=None):
        report = run_governed_production_workflow(
            tables,
            config,
            reference_tables=reference_tables,
            calibration_labels=calibration_labels,
        )
        artifacts = report.get("artifacts", {})
        governance = artifacts.get("governance", {})
        readiness = artifacts.get("production_readiness", {})
        recommendation = {
            "decision": governance.get("consensus", {}).get("decision"),
            "dossier": governance.get("dossier", {}),
        }
        case = self.store.add_case(
            recommendation=recommendation,
            governance_decision=recommendation["decision"] or "INSUFFICIENT_EVIDENCE",
            production_readiness=readiness.get("grade", "laboratory_only"),
        )
        report.setdefault("artifacts", {})["shadow_case"] = case.to_dict()
        return report
