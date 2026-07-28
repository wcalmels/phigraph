from phigraph.benchmark import make_synthetic_fleet
from phigraph.benchmark.kernel_ablation import run_kernel_ablation

def test_kernel_ablation():
    result = run_kernel_ablation(make_synthetic_fleet(n_trucks=40,seed=47))
    assert len(result.ranking) == 6
    assert "signal_aware" in result.methods
