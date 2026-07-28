from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

from .governance_workflow import GovernanceWorkflowConfig, run_governed_production_workflow
from .shadow import ShadowDeploymentStore, compute_shadow_metrics

@dataclass(frozen=True)
class ShadowWorkflowConfig(GovernanceWorkflowConfig):
    shadow_store_path: str = "data/shadow_deployment.json"

def run_shadow_deployment_workflow(
    tables: dict[str, pd.DataFrame],
    config: ShadowWorkflowConfig = ShadowWorkflowConfig(),
    *,
    reference_tables=None,
    calibration_labels=None,
):
    report = run_governed_production_workflow(
        tables,
        config,
        reference_tables=reference_tables,
        calibration_labels=calibration_labels,
    )
    store = ShadowDeploymentStore(config.shadow_store_path)
    artifacts = report.get("artifacts", {})
    governance = artifacts.get("governance", {})
    readiness = artifacts.get("production_readiness", {})
    case = store.add_case(
        recommendation={
            "decision": governance.get("consensus", {}).get("decision"),
            "dossier": governance.get("dossier", {}),
        },
        governance_decision=governance.get("consensus", {}).get(
            "decision", "INSUFFICIENT_EVIDENCE"
        ),
        production_readiness=readiness.get("grade", "laboratory_only"),
    )
    metrics = compute_shadow_metrics(store.list_cases(), store.list_outcomes())
    report["artifacts"]["shadow_case"] = case.to_dict()
    report["artifacts"]["shadow_metrics"] = metrics.to_dict()
    report["results"].append({
        "agent": "shadow_deployment",
        "status": "ok",
        "summary": "Shadow recommendation recorded without execution.",
        "outputs": {
            "shadow_case": case.to_dict(),
            "shadow_metrics": metrics.to_dict(),
        },
    })
    return report
