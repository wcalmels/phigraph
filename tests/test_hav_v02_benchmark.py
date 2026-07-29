from phigraph.hav.adapters import repository_state
from phigraph.hav.benchmark import BenchmarkCase, BenchmarkRunner


def test_benchmark_runner():
    state = repository_state(
        tests_passed=117, tests_total=117, ci_status="passed", codeql_status="failed",
        package_status="passed", docker_status="passed", release_gate_status="blocked",
    )
    result = BenchmarkRunner().run([BenchmarkCase(
        case_id="global", candidate_output="Todos los controles pasaron.",
        state=state, expected_verdict="REJECT", category="state",
    )])
    assert result.accuracy == 1.0
