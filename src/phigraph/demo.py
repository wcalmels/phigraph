from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .ablation import AblationEngine
from .corridors import CorridorAnalyzer
from .graph import GraphDataset
from .localization import HotspotLocator
from .reporting import save_json_report
from .spectral import SpectralAnalyzer


def run_demo(output: str | Path) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    nodes = [f"truck-{i:02d}" for i in range(1, 13)]
    rows = []
    for i, node in enumerate(nodes):
        rows.append((node, nodes[(i + 1) % len(nodes)], 1.0))
        rows.append((node, nodes[(i + 3) % len(nodes)], 0.6))
    edges = pd.DataFrame(rows, columns=["source", "target", "weight"])

    rng = np.random.default_rng(47)
    signals = {node: float(rng.normal(0, 0.15)) for node in nodes}
    for node in ["truck-03", "truck-04", "truck-05"]:
        signals[node] += 2.0

    dataset = GraphDataset.from_edge_table(
        edges,
        source="source",
        target="target",
        weight="weight",
        node_signal=signals,
    )

    # Reweight graph from signal differences.
    index = {node: i for i, node in enumerate(dataset.nodes)}
    for u, v in dataset.graph.edges():
        dataset.graph[u][v]["weight"] = (
            0.05
            + np.exp(-0.35 * abs(dataset.signal[index[u]] - dataset.signal[index[v]]))
        )

    spectrum = SpectralAnalyzer(dataset).analyze(k=8)
    mode = int(np.argmax(spectrum.ipr))
    locator = HotspotLocator(dataset, spectrum)
    hotspot = locator.top_nodes(mode, fraction=0.25)

    engine = AblationEngine(dataset, spectrum)
    intervention = engine.neutralize_nodes(hotspot, mode=mode)
    controls = engine.matched_node_controls(hotspot, n_controls=50)
    control_drops = [
        engine.neutralize_nodes(region, mode=mode).relative_drop
        for region in controls
    ]
    pvalue = engine.empirical_pvalue(intervention.relative_drop, control_drops)

    corridors = CorridorAnalyzer(dataset, spectrum).progressive_components(mode)

    report = {
        "mode": mode,
        "mean_gap_ratio": spectrum.mean_gap_ratio,
        "mode_ipr": float(spectrum.ipr[mode]),
        "hotspot_nodes": hotspot,
        "intervention": intervention.__dict__,
        "empirical_pvalue": pvalue,
        "corridors": corridors,
    }
    return save_json_report(report, output / "report.json")
