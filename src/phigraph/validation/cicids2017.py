from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
)
from sklearn.neighbors import LocalOutlierFactor, NearestNeighbors
from sklearn.preprocessing import RobustScaler


@dataclass(frozen=True)
class CICIDSValidationConfig:
    seed: int = 47
    train_benign: int = 12000
    test_benign: int = 6000
    test_attack: int = 6000
    n_features: int = 24
    graph_neighbors: int = 15
    top_fraction: float = 0.10

    def to_dict(self):
        return asdict(self)


def _clean_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def _binary_label(series: pd.Series) -> np.ndarray:
    return (
        series.astype(str).str.strip().str.upper() != "BENIGN"
    ).astype(int).to_numpy()


def _prepare_numeric(frame: pd.DataFrame) -> pd.DataFrame:
    numeric = frame.drop(columns=["Label"], errors="ignore").apply(
        pd.to_numeric,
        errors="coerce",
    )
    numeric = numeric.replace([np.inf, -np.inf], np.nan)
    numeric = numeric.loc[:, numeric.notna().any(axis=0)]
    return numeric


def _select_features(
    train: pd.DataFrame,
    test: pd.DataFrame,
    n_features: int,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    medians = train.median()
    train = train.fillna(medians)
    test = test.fillna(medians)

    variability = train.nunique()
    keep = variability[variability > 1].index
    train = train[keep]
    test = test[keep]

    q25 = train.quantile(0.25)
    q75 = train.quantile(0.75)
    iqr = (q75 - q25).replace(0, np.nan)
    robust_variability = (iqr / (train.abs().median() + 1e-9)).replace(
        [np.inf, -np.inf], np.nan
    ).fillna(0)
    selected = (
        robust_variability.sort_values(ascending=False)
        .head(n_features)
        .index.tolist()
    )
    return train[selected], test[selected], selected


def _robust_distance(train_x: np.ndarray, test_x: np.ndarray) -> np.ndarray:
    center = np.median(train_x, axis=0)
    scale = np.median(np.abs(train_x - center), axis=0) * 1.4826
    scale = np.where(scale < 1e-6, 1.0, scale)
    z = np.abs((test_x - center) / scale)
    return np.mean(np.clip(z, 0, 10), axis=1)


def _knn_relational_score(
    train_x: np.ndarray,
    test_x: np.ndarray,
    *,
    neighbors: int,
) -> np.ndarray:
    model = NearestNeighbors(
        n_neighbors=neighbors,
        metric="euclidean",
        n_jobs=-1,
    )
    model.fit(train_x)
    distances, _ = model.kneighbors(test_x)
    local_distance = distances.mean(axis=1)
    local_spread = distances.std(axis=1)
    return local_distance + 0.35 * local_spread


def _phigraph_score(
    train_x: np.ndarray,
    test_x: np.ndarray,
    *,
    neighbors: int,
) -> np.ndarray:
    robust = _robust_distance(train_x, test_x)
    relational = _knn_relational_score(
        train_x,
        test_x,
        neighbors=neighbors,
    )

    robust_rank = pd.Series(robust).rank(pct=True).to_numpy()
    relational_rank = pd.Series(relational).rank(pct=True).to_numpy()

    # Multi-kernel proxy: robust feature deviation + local graph-distance
    # disagreement. This is intentionally label-free.
    disagreement = np.abs(robust_rank - relational_rank)
    return (
        0.50 * robust_rank
        + 0.40 * relational_rank
        + 0.10 * disagreement
    )


def _metrics(
    labels: np.ndarray,
    scores: np.ndarray,
    top_fraction: float,
) -> dict:
    threshold = np.quantile(scores, 1.0 - top_fraction)
    predicted = (scores >= threshold).astype(int)
    positives = int(predicted.sum())
    return {
        "roc_auc": float(roc_auc_score(labels, scores)),
        "pr_auc": float(average_precision_score(labels, scores)),
        "precision_at_top_fraction": float(
            precision_score(labels, predicted, zero_division=0)
        ),
        "recall_at_top_fraction": float(
            recall_score(labels, predicted, zero_division=0)
        ),
        "f1_at_top_fraction": float(
            f1_score(labels, predicted, zero_division=0)
        ),
        "top_fraction": float(top_fraction),
        "flagged": positives,
        "threshold": float(threshold),
    }


def run_cicids2017_validation(
    csv_path: str | Path,
    output_dir: str | Path,
    config: CICIDSValidationConfig = CICIDSValidationConfig(),
) -> dict:
    started = time.perf_counter()
    csv_path = Path(csv_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = _clean_columns(pd.read_csv(csv_path))
    labels_all = _binary_label(frame["Label"])
    benign = frame.loc[labels_all == 0].copy()
    attack = frame.loc[labels_all == 1].copy()

    rng = np.random.default_rng(config.seed)
    benign_idx = rng.permutation(len(benign))
    attack_idx = rng.permutation(len(attack))

    train_frame = benign.iloc[
        benign_idx[: config.train_benign]
    ].copy()
    test_benign = benign.iloc[
        benign_idx[
            config.train_benign:
            config.train_benign + config.test_benign
        ]
    ].copy()
    test_attack = attack.iloc[
        attack_idx[: config.test_attack]
    ].copy()
    test_frame = pd.concat(
        [test_benign, test_attack],
        ignore_index=True,
    )
    test_labels = _binary_label(test_frame["Label"])

    permutation = rng.permutation(len(test_frame))
    test_frame = test_frame.iloc[permutation].reset_index(drop=True)
    test_labels = test_labels[permutation]

    train_numeric = _prepare_numeric(train_frame)
    test_numeric = _prepare_numeric(test_frame)
    train_numeric, test_numeric, selected = _select_features(
        train_numeric,
        test_numeric,
        config.n_features,
    )

    scaler = RobustScaler(quantile_range=(10, 90))
    train_x = scaler.fit_transform(train_numeric)
    test_x = scaler.transform(test_numeric)
    train_x = np.nan_to_num(train_x, nan=0.0, posinf=20.0, neginf=-20.0)
    test_x = np.nan_to_num(test_x, nan=0.0, posinf=20.0, neginf=-20.0)
    train_x = np.clip(train_x, -20, 20)
    test_x = np.clip(test_x, -20, 20)

    scores: dict[str, np.ndarray] = {}
    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    scores["robust_z"] = _robust_distance(train_x, test_x)
    timings["robust_z"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    isolation = IsolationForest(
        n_estimators=200,
        contamination="auto",
        random_state=config.seed,
        n_jobs=-1,
    )
    isolation.fit(train_x)
    scores["isolation_forest"] = -isolation.score_samples(test_x)
    timings["isolation_forest"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    lof = LocalOutlierFactor(
        n_neighbors=35,
        novelty=True,
        contamination="auto",
        n_jobs=-1,
    )
    lof.fit(train_x)
    scores["local_outlier_factor"] = -lof.score_samples(test_x)
    timings["local_outlier_factor"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    scores["phigraph_relational"] = _phigraph_score(
        train_x,
        test_x,
        neighbors=config.graph_neighbors,
    )
    timings["phigraph_relational"] = time.perf_counter() - t0

    results = {
        name: {
            **_metrics(
                test_labels,
                score,
                config.top_fraction,
            ),
            "runtime_seconds": float(timings[name]),
        }
        for name, score in scores.items()
    }

    predictions = pd.DataFrame(
        {
            "label": test_labels,
            **{
                f"score_{name}": values
                for name, values in scores.items()
            },
        }
    )
    predictions.to_csv(
        output_dir / "predictions.csv",
        index=False,
    )

    summary_rows = [
        {"method": name, **metrics}
        for name, metrics in results.items()
    ]
    pd.DataFrame(summary_rows).sort_values(
        "pr_auc",
        ascending=False,
    ).to_csv(
        output_dir / "metrics.csv",
        index=False,
    )

    report = {
        "dataset": {
            "name": "CIC-IDS2017",
            "file": csv_path.name,
            "total_rows": int(len(frame)),
            "benign_rows": int(len(benign)),
            "attack_rows": int(len(attack)),
            "labels": {
                str(key).strip(): int(value)
                for key, value in frame["Label"].value_counts().items()
            },
        },
        "protocol": {
            "training": "benign-only, label used solely for benchmark split",
            "test": "balanced benign/DDoS holdout",
            "split_seed": config.seed,
            "train_benign": len(train_frame),
            "test_benign": len(test_benign),
            "test_attack": len(test_attack),
            "selected_features": selected,
            "top_fraction": config.top_fraction,
        },
        "results": results,
        "limitations": [
            "MachineLearningCSV omits source IP, destination IP, timestamp and identity fields.",
            "This validates flow-level anomaly ranking and similarity-graph scoring, not identity-device-process attack paths.",
            "The split is a controlled benchmark, not a prospective deployment.",
            "CIC-IDS2017 has documented flow construction and labeling issues; results must not be treated as production evidence.",
        ],
        "elapsed_seconds": float(time.perf_counter() - started),
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return report
