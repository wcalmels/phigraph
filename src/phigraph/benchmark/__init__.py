"""Formal benchmarking suite for PhiGraph Causal."""

from .datasets import BenchmarkDataset, make_synthetic_fleet, make_synthetic_fraud
from .metrics import BenchmarkMetrics, evaluate_detection, evaluate_localization
from .runner import BenchmarkConfig, BenchmarkResult, run_benchmark
from .report import save_benchmark_report

__all__ = [
    "BenchmarkDataset",
    "make_synthetic_fleet",
    "make_synthetic_fraud",
    "BenchmarkMetrics",
    "evaluate_detection",
    "evaluate_localization",
    "BenchmarkConfig",
    "BenchmarkResult",
    "run_benchmark",
    "save_benchmark_report",
]

from .kernel_ablation import KernelAblationResult, run_kernel_ablation
