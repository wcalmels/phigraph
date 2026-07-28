from dataclasses import dataclass, asdict
import numpy as np
from .spectral import analyze_kernel

@dataclass(frozen=True)
class KernelSelection:
    selected_kernel: str
    scores: dict[str, float]
    diagnostics: dict[str, dict]
    reasons: tuple[str, ...]
    def to_dict(self):
        return asdict(self)

def select_kernel(context, kernels, k=10):
    scores, diagnostics = {}, {}
    for name, kernel in kernels.items():
        try:
            result = kernel.build(context)
            spectrum = analyze_kernel(result, k=k)
            max_ipr = float(np.max(spectrum.ipr))
            spread = float(np.std(spectrum.ipr))
            norm_penalty = float(np.log1p(np.linalg.norm(result.operator.toarray(), 2)))
            scores[name] = max_ipr + 0.25*spread - 0.01*norm_penalty
            diagnostics[name] = {
                "max_ipr": max_ipr,
                "ipr_std": spread,
                "operator_norm_penalty": norm_penalty,
                "nodes": len(result.nodes),
            }
        except Exception as exc:
            scores[name] = float("-inf")
            diagnostics[name] = {"error": str(exc)}
    valid = {name: score for name, score in scores.items() if np.isfinite(score)}
    if not valid:
        raise ValueError("No candidate kernel could be evaluated.")
    selected = max(valid, key=valid.get)
    return KernelSelection(
        selected, {k: float(v) for k, v in scores.items()}, diagnostics,
        ("localization concentration and operator complexity heuristic",
         "selection is benchmark-dependent, not causal proof"),
    )
