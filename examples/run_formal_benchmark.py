from phigraph.benchmark import (
    BenchmarkConfig,
    make_synthetic_fleet,
    run_benchmark,
    save_benchmark_report,
)

dataset = make_synthetic_fleet(n_trucks=80, seed=47)
result = run_benchmark(
    dataset,
    BenchmarkConfig(n_null_controls=10, seed=47),
)
print(result.ranking)
print(save_benchmark_report(result, "results/formal_benchmark"))
