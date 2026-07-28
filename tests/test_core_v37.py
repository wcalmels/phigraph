from pathlib import Path

from phigraph.core_v3.code_benchmark import AgentReport, CodeVerifier, ModelRun, MultiModelBenchmarkSuite, benchmark_markdown, save_benchmark_report
from phigraph.core_v3.github_readonly import GitHubReadOnlyConnector


def fixture_repo(root: Path, failing: bool = False):
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    assertion = "False" if failing else "True"
    (root / "tests" / "test_app.py").write_text(f"def test_value():\n    assert {assertion}\n", encoding="utf-8")


def test_multimodel_suite_aggregates_false_claims(tmp_path: Path):
    fixture_repo(tmp_path, failing=True)
    runs = [ModelRun("small", AgentReport("small", ({"statement":"tests pass", "requires_check":"tests"},), True), .01, 50), ModelRun("frontier", AgentReport("frontier", ({"statement":"tests pass", "requires_check":"tests"},), True), .2, 100)]
    result = MultiModelBenchmarkSuite(tmp_path).run(runs)
    assert result["summary"]["models"] == 2
    assert result["summary"]["completion_blocks"] == 2
    assert result["summary"]["governed_false_claims"] == 0


def test_benchmark_report_artifacts(tmp_path: Path):
    fixture_repo(tmp_path)
    result = MultiModelBenchmarkSuite(tmp_path).run([ModelRun("m", AgentReport("m", (), True))])
    paths = save_benchmark_report(tmp_path / "reports", result)
    assert Path(paths["json"]).exists()
    assert "PhiGraph Code Benchmark Report" in Path(paths["markdown"]).read_text()
    assert "Models evaluated" in benchmark_markdown(result)


def test_github_connector_is_read_only_and_filters_prs():
    calls=[]
    def fetch(url, headers):
        calls.append(url)
        if "/issues?" in url:
            return [{"number":1,"title":"Issue","body":"x","state":"open","html_url":"u"}, {"number":2,"title":"PR","body":"y","state":"open","html_url":"p","pull_request":{}}]
        return {"default_branch":"main","private":False,"html_url":"repo","archived":False}
    connector=GitHubReadOnlyConnector(fetcher=fetch)
    assert connector.repository("o","r")["default_branch"] == "main"
    assert len(connector.issues("o","r")) == 2
    assert len(connector.pull_requests("o","r")) == 1
    assert all("/repos/o/r" in x for x in calls)


def test_extended_verifier_allowlist(tmp_path: Path):
    fixture_repo(tmp_path)
    verifier=CodeVerifier(tmp_path)
    assert verifier._command("lint")[2:4] == ["ruff", "check"]
    assert verifier._command("typecheck")[2:4] == ["mypy", "src"]
