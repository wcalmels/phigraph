from __future__ import annotations

import numpy as np

from phigraph.advanced_meta_workflow import AdvancedMetaConfig, run_advanced_meta_workflow


class PhiGraphBenchmarkAdapter:
    name = "phigraph_v1"

    def __init__(self, *, n_null_controls: int = 10, seed: int = 47):
        self.n_null_controls = n_null_controls
        self.seed = seed

    def score(self, dataset) -> tuple[np.ndarray, dict]:
        report = run_advanced_meta_workflow(
            dataset.tables,
            AdvancedMetaConfig(
                domain=dataset.domain,
                n_null_controls=self.n_null_controls,
                seed=self.seed,
                temporal_values=(),
                confirmed_outcome=False,
                meta_store_path=":memory:",
            ),
        )

        root = report["artifacts"].get("projected_root_cause", {})
        hotspot = set(root.get("hotspot_nodes", []))
        edge_rows = root.get("top_edges", [])

        # Map heterogeneous node labels back to canonical entity IDs.
        raw_scores = {entity: 0.0 for entity in dataset.entity_ids}
        for rank, node in enumerate(root.get("hotspot_nodes", []), start=1):
            for entity in dataset.entity_ids:
                canonical = entity.lower().replace("klg-", "")
                if canonical and canonical in str(node).lower().replace("klg-", ""):
                    raw_scores[entity] = max(raw_scores[entity], 1.0 / rank)

        for row in edge_rows:
            energy = float(row.get("energy", 0.0))
            combined = f"{row.get('source','')} {row.get('target','')}".lower()
            for entity in dataset.entity_ids:
                canonical = entity.lower().replace("klg-", "")
                if canonical and canonical in combined.replace("klg-", ""):
                    raw_scores[entity] += energy

        scores = np.array([raw_scores[entity] for entity in dataset.entity_ids], dtype=float)

        # Fallback: use numerical structural deviation when entity mapping is sparse.
        if np.count_nonzero(scores) < max(2, len(dataset.causal_entities)):
            numeric = dataset.entity_features.select_dtypes(include="number").drop(
                columns=["label"], errors="ignore"
            ).to_numpy(dtype=float)
            median = np.median(numeric, axis=0)
            mad = np.median(np.abs(numeric - median), axis=0)
            scale = np.where(1.4826 * mad > 1e-12, 1.4826 * mad, np.std(numeric, axis=0) + 1e-12)
            fallback = np.sqrt(np.sum(((numeric - median) / scale) ** 2, axis=1))
            scores = scores + fallback / max(float(np.max(fallback)), 1e-12)

        diagnostics = {
            "null_controls": report["artifacts"].get("null_controls", {}),
            "adversarial_validation": report["artifacts"].get("adversarial_validation", {}),
            "projection": report["artifacts"].get("projection", {}),
        }
        return scores, diagnostics
