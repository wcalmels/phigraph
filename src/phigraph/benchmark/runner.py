from __future__ import annotations

from dataclasses import dataclass, asdict
from time import perf_counter
from typing import Any
import numpy as np

from .baselines import (
    IsolationForestBaseline,
    LOFBaseline,
    OneClassSVMBaseline,
    RobustZScoreBaseline,
)
from .metrics import BenchmarkMetrics, evaluate_detection, evaluate_localization
from .phigraph_adapter import PhiGraphBenchmarkAdapter


@dataclass(frozen=True)
class BenchmarkConfig:
    contamination: float = 0.10
    n_null_controls: int = 10
    seed: int = 47
    methods: tuple[str, ...] = (
        "phigraph_v1",
        "robust_zscore",
        "isolation_forest",
        "local_outlier_factor",
        "one_class_svm",
    )


@dataclass(frozen=True)
class BenchmarkResult:
    dataset: dict
    methods: dict[str, dict]
    ranking: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "methods": self.methods,
            "ranking": list(self.ranking),
        }


def _build_methods(config: BenchmarkConfig):
    registry = {
        "phigraph_v1": PhiGraphBenchmarkAdapter(
            n_null_controls=config.n_null_controls,
            seed=config.seed,
        ),
        "robust_zscore": RobustZScoreBaseline(),
        "isolation_forest": IsolationForestBaseline(
            contamination=config.contamination,
            seed=config.seed,
        ),
        "local_outlier_factor": LOFBaseline(
            contamination=config.contamination,
        ),
        "one_class_svm": OneClassSVMBaseline(
            nu=config.contamination,
        ),
    }
    return [registry[name] for name in config.methods]


def run_benchmark(dataset, config: BenchmarkConfig = BenchmarkConfig()) -> BenchmarkResult:
    method_results: dict[str, dict[str, Any]] = {}

    for method in _build_methods(config):
        started = perf_counter()
        diagnostics = {}
        if method.name == "phigraph_v1":
            scores, diagnostics = method.score(dataset)
        else:
            scores = method.score(dataset.entity_features)
        runtime = perf_counter() - started

        detection = evaluate_detection(dataset.labels, scores)
        localization = evaluate_localization(
            dataset.entity_ids,
            scores,
            dataset.causal_entities,
        )
        stability = None
        if method.name == "phigraph_v1":
            stability = diagnostics.get(
                "adversarial_validation", {}
            ).get("stability_score")

        metrics = BenchmarkMetrics(
            **detection,
            **localization,
            runtime_seconds=float(runtime),
            stability=None if stability is None else float(stability),
        )
        method_results[method.name] = {
            "metrics": metrics.to_dict(),
            "diagnostics": diagnostics,
            "score_summary": {
                "min": float(np.min(scores)),
                "max": float(np.max(scores)),
                "mean": float(np.mean(scores)),
            },
        }

    ranking = tuple(
        sorted(
            method_results,
            key=lambda name: (
                method_results[name]["metrics"]["f1"],
                method_results[name]["metrics"]["localization_recall_at_k"],
                method_results[name]["metrics"]["auprc"],
            ),
            reverse=True,
        )
    )

    return BenchmarkResult(
        dataset=dataset.to_dict(),
        methods=method_results,
        ranking=ranking,
    )
