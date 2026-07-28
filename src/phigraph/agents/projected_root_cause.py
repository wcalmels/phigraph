from __future__ import annotations

import numpy as np

from phigraph.localization import HotspotLocator
from phigraph.spectral import SpectralAnalyzer
from .base import AgentContext, AgentResult


class ProjectedRootCauseAgent:
    name = "projected_root_cause"

    def run(self, context: AgentContext) -> AgentResult:
        dataset = context.artifacts.get("_projection_dataset")
        if dataset is None:
            return AgentResult(self.name, "blocked", "Projection is unavailable.", {})

        normalized = bool(context.payload.get("normalized_laplacian", False))
        modes = int(context.payload.get("spectral_modes", 10))
        fraction = float(context.payload.get("hotspot_fraction", 0.10))
        spectrum = SpectralAnalyzer(dataset, normalized=normalized).analyze(
            k=min(modes, dataset.size - 1)
        )
        mode = int(np.argmax(spectrum.ipr))
        locator = HotspotLocator(dataset, spectrum)
        hotspot = locator.top_nodes(mode, fraction)
        output = {
            "dominant_mode": mode,
            "dominant_ipr": float(spectrum.ipr[mode]),
            "mean_gap_ratio": spectrum.mean_gap_ratio,
            "hotspot_nodes": [str(node) for node in hotspot],
            "top_edges": [
                {"source": str(u), "target": str(v), "energy": energy}
                for u, v, energy in locator.edge_energy(mode)[:10]
            ],
        }
        context.artifacts["_projection_spectrum"] = spectrum
        context.artifacts["projected_root_cause"] = output
        context.artifacts["hotspot"] = [str(node) for node in hotspot]
        context.record(self.name, "analyze_projected_graph", output)
        return AgentResult(
            self.name,
            "ok",
            f"Localized {len(hotspot)} projected hotspot nodes.",
            output,
        )
