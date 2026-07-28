from __future__ import annotations

import numpy as np

from phigraph.ablation import AblationEngine
from .base import AgentContext, AgentResult


class SimulationAgent:
    name = "simulation"

    def run(self, context: AgentContext) -> AgentResult:
        dataset = context.artifacts.get("dataset")
        spectrum = context.artifacts.get("spectrum")
        hotspot = context.artifacts.get("hotspot")
        if dataset is None or spectrum is None or not hotspot:
            return AgentResult(
                self.name,
                "blocked",
                "Dataset, spectrum, and hotspot are required.",
                {},
            )

        mode = int(np.argmax(spectrum.ipr))
        engine = AblationEngine(dataset, spectrum)
        observed = engine.neutralize_nodes(hotspot, mode=mode)
        n_controls = int(context.payload.get("n_controls", 50))
        controls = engine.matched_node_controls(
            hotspot,
            n_controls=n_controls,
            seed=int(context.payload.get("seed", 47)),
        )
        control_drops = [
            engine.neutralize_nodes(region, mode=mode).relative_drop
            for region in controls
        ]
        pvalue = engine.empirical_pvalue(observed.relative_drop, control_drops)

        output = {
            "intervention": "neutralize_hotspot_nodes",
            "relative_drop": observed.relative_drop,
            "mode_overlap": observed.overlap,
            "tracked_mode": observed.tracked_mode,
            "empirical_pvalue": pvalue,
            "control_mean": float(np.mean(control_drops)),
            "control_std": float(np.std(control_drops)),
        }
        context.artifacts["simulation"] = output
        context.record(self.name, "run_counterfactual_ablation", output)
        return AgentResult(
            self.name,
            "ok",
            f"Intervention changed the target IPR by {observed.relative_drop:.1%}.",
            output,
        )
