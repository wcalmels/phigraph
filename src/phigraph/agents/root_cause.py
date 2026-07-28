from __future__ import annotations

import numpy as np

from phigraph.localization import HotspotLocator
from phigraph.spectral import SpectralAnalyzer
from .base import AgentContext, AgentResult


class RootCauseAgent:
    name = "root_cause"

    def run(self, context: AgentContext) -> AgentResult:
        dataset = context.artifacts.get("dataset")
        if dataset is None:
            return AgentResult(self.name, "blocked", "Graph has not been built.", {})

        k = int(context.payload.get("spectral_modes", min(10, dataset.size - 1)))
        spectrum = SpectralAnalyzer(
            dataset,
            normalized=bool(context.payload.get("normalized_laplacian", False)),
        ).analyze(k=k)
        mode = int(np.argmax(spectrum.ipr))
        fraction = float(context.payload.get("hotspot_fraction", 0.10))
        locator = HotspotLocator(dataset, spectrum)
        hotspot = locator.top_nodes(mode, fraction=fraction)
        edge_energy = locator.edge_energy(mode)[:10]

        context.artifacts["spectrum"] = spectrum
        context.artifacts["hotspot"] = hotspot
        output = {
            "dominant_mode": mode,
            "dominant_ipr": float(spectrum.ipr[mode]),
            "mean_gap_ratio": spectrum.mean_gap_ratio,
            "hotspot_nodes": hotspot,
            "top_edges": [
                {"source": u, "target": v, "energy": energy}
                for u, v, energy in edge_energy
            ],
        }
        context.record(self.name, "localize_root_cause_candidates", output)
        return AgentResult(
            self.name,
            "ok",
            f"Localized {len(hotspot)} root-cause candidates.",
            output,
        )
