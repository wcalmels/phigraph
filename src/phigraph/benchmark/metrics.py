from __future__ import annotations

from dataclasses import dataclass, asdict
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    precision_recall_fscore_support,
    roc_auc_score,
)


@dataclass(frozen=True)
class BenchmarkMetrics:
    precision: float
    recall: float
    f1: float
    auroc: float
    auprc: float
    localization_precision_at_k: float
    localization_recall_at_k: float
    mean_rank_causal: float
    runtime_seconds: float
    stability: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_detection(
    labels,
    scores,
    *,
    threshold: float | None = None,
) -> dict[str, float]:
    labels = np.asarray(labels, dtype=int)
    scores = np.asarray(scores, dtype=float)
    if labels.shape != scores.shape:
        raise ValueError("labels and scores must have the same shape")

    if threshold is None:
        positives = max(1, int(np.sum(labels)))
        cutoff = np.argsort(scores)[-positives:]
        predictions = np.zeros_like(labels)
        predictions[cutoff] = 1
    else:
        predictions = (scores >= threshold).astype(int)

    precision, recall, f1, _ = precision_recall_fscore_support(
        labels,
        predictions,
        average="binary",
        zero_division=0,
    )
    auroc = roc_auc_score(labels, scores) if len(np.unique(labels)) > 1 else float("nan")
    auprc = average_precision_score(labels, scores)

    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "auroc": float(auroc),
        "auprc": float(auprc),
    }


def evaluate_localization(
    entity_ids,
    scores,
    causal_entities,
    *,
    k: int | None = None,
) -> dict[str, float]:
    entity_ids = np.asarray(entity_ids, dtype=object)
    scores = np.asarray(scores, dtype=float)
    causal = set(causal_entities)
    if k is None:
        k = max(1, len(causal))
    ranked_indices = np.argsort(scores)[::-1]
    ranked_entities = entity_ids[ranked_indices]
    top = set(ranked_entities[:k].tolist())

    intersection = top & causal
    precision = len(intersection) / max(len(top), 1)
    recall = len(intersection) / max(len(causal), 1)

    ranks = {
        entity: rank + 1
        for rank, entity in enumerate(ranked_entities.tolist())
    }
    mean_rank = float(
        np.mean([ranks[entity] for entity in causal if entity in ranks])
    ) if causal else float("nan")

    return {
        "localization_precision_at_k": float(precision),
        "localization_recall_at_k": float(recall),
        "mean_rank_causal": mean_rank,
    }
