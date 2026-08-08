from pathlib import Path

import pytest

from phigraph.core_v3.code_benchmark import AgentReport, CodeVerifier, GitHubRepositoryDescriptor, PhiGraphCodeBenchmark, RepositoryIndexer


def test_repository_indexer_extracts_python_symbols(tmp_path: Path):
    (tmp_path / "mod.py").write_text("class A:\n    pass\n\ndef f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "test_mod.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    snapshot = RepositoryIndexer(tmp_path).build()
    fact = next(x for x in snapshot.facts if x.path == "mod.py")
    assert fact.symbols == ("A", "f")
    assert snapshot.test_files == ("test_mod.py",)


def test_code_verifier_rejects_arbitrary_commands(tmp_path: Path):
    with pytest.raises(ValueError, match="unsupported_check"):
        CodeVerifier(tmp_path).run("shell")


def test_governed_benchmark_requires_evidence(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    report = AgentReport("small-model", ({"statement": "tests pass", "requires_check": "tests"},), True)
    result = PhiGraphCodeBenchmark(tmp_path).compare(report)
    assert result["baseline"]["task_accepted_complete"] is True
    assert result["governed"]["task_accepted_complete"] is True
    assert result["governed"]["checks"][1]["passed"] is True


def test_governed_benchmark_blocks_false_completion(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    report = AgentReport("small-model", ({"statement": "compile passes", "requires_check": "compile"},), True)
    result = PhiGraphCodeBenchmark(tmp_path).compare(report)
    assert result["baseline"]["task_accepted_complete"] is True
    assert result["governed"]["task_accepted_complete"] is False
    assert result["delta"]["completion_blocked"] is True


def test_github_descriptor_is_provider_neutral_context():
    descriptor = GitHubRepositoryDescriptor("wcalmels", "phigraph", commit_sha="abc123")
    assert descriptor.canonical_id == "github:wcalmels/phigraph@abc123"
    assert descriptor.to_context()["provider"] == "github"


def test_code_benchmark_api(tmp_path: Path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from phigraph.core_v3.api import create_core_v3_router

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    data = tmp_path / "data"
    app = FastAPI()
    app.include_router(create_core_v3_router(data, allow_unauthenticated_dev=True))
    response = TestClient(app).post("/v3/code/benchmark", json={
        "repository_path": str(tmp_path),
        "agent": "small-model",
        "claims": [{"statement": "tests pass", "requires_check": "tests"}],
        "declared_complete": True,
    })
    assert response.status_code == 200
    assert response.json()["governed"]["task_accepted_complete"] is True
