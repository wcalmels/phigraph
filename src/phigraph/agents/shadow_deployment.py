from phigraph.shadow import ShadowDeploymentStore, ShadowDeploymentRunner
from .base import AgentContext, AgentResult

class ShadowDeploymentAgent:
    name = "shadow_deployment"

    def run(self, context):
        report = context.payload.get("governed_report")
        if report is None:
            return AgentResult(self.name, "blocked", "Governed report required.", {})
        store = ShadowDeploymentStore(
            context.payload.get("shadow_store_path", "data/shadow_deployment.json")
        )
        artifacts = report.get("artifacts", {})
        governance = artifacts.get("governance", {})
        readiness = artifacts.get("production_readiness", {})
        recommendation = {
            "decision": governance.get("consensus", {}).get("decision"),
            "dossier": governance.get("dossier", {}),
        }
        case = store.add_case(
            recommendation=recommendation,
            governance_decision=recommendation["decision"] or "INSUFFICIENT_EVIDENCE",
            production_readiness=readiness.get("grade", "laboratory_only"),
        )
        output = {"shadow_case": case.to_dict(), "executed": False}
        context.artifacts["shadow_deployment"] = output
        context.record(self.name, "record_shadow_case", output)
        return AgentResult(self.name, "ok", "Shadow case recorded without execution.", output)
