import io
import json
import subprocess
import tarfile
from pathlib import Path

from phigraph.core_v3.code_v38 import PatchProposal
from phigraph.core_v3.code_v39 import (
    CorpusExperimentRunner,
    CorpusTask,
    DependencyInventory,
    DeterministicSecurityScanner,
    GitHubCommitArchiveFetcher,
    OpenAICompatibleModelAdapter,
    PatchQualityEvaluator,
    ReproducibleCorpus,
    save_scientific_report,
)


def make_repo(root: Path):
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("def value():\n    return 1\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_app.py").write_text("from src.app import value\ndef test_value(): assert value()==1\n")
    (root / "pyproject.toml").write_text('[project]\nname="fixture"\ndependencies=["requests>=2"]\n')
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def patch_value():
    return '''diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
 def value():
-    return 1
+    return 2
'''


def test_corpus_round_trip_and_hash(tmp_path: Path):
    corpus = ReproducibleCorpus([CorpusTask("T1", "Change", "Change value", "repo", "abcdef1")])
    path = corpus.save_jsonl(tmp_path / "corpus.jsonl")
    loaded = ReproducibleCorpus.load_jsonl(path)
    assert loaded.sha256 == corpus.sha256 and loaded.to_dict()["count"] == 1


def test_model_adapter_measures_usage_and_cost():
    def transport(endpoint, headers, payload):
        return {"choices": [{"message": {"content": json.dumps({"patch": "", "declared_complete": False})}}], "usage": {"prompt_tokens": 1000, "completion_tokens": 500}}
    adapter = OpenAICompatibleModelAdapter("m", "https://example.invalid", transport=transport, input_cost_per_million=1, output_cost_per_million=2)
    result = adapter.propose({"id": "T"}, {"x": 1})
    assert result.input_tokens == 1000 and result.output_tokens == 500 and result.cost_usd == 0.002


def test_security_scanner_and_dependency_inventory(tmp_path: Path):
    (tmp_path / "app.py").write_text('api_key = "123456789-secret"\n')
    (tmp_path / "requirements.txt").write_text("requests>=2\n")
    findings = DeterministicSecurityScanner().scan(tmp_path)
    inventory = DependencyInventory().build(tmp_path)
    assert findings[0].rule == "hardcoded-secret" and inventory["count"] == 1


def test_patch_quality_preserves_source(tmp_path: Path):
    make_repo(tmp_path)
    before = (tmp_path / "src" / "app.py").read_text()
    result = PatchQualityEvaluator(tmp_path).evaluate(PatchProposal(patch_value(), "model", "T1"), checks=("compile",))
    assert result["applied"] and result["quality_gate"]["accepted"]
    assert result["patch_stats"]["changed_lines"] == 2
    assert (tmp_path / "src" / "app.py").read_text() == before


def test_github_archive_safe_extract(tmp_path: Path):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        data = b"ok"
        info = tarfile.TarInfo("owner-repo/src/a.py")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    fetcher = GitHubCommitArchiveFetcher(fetcher=lambda url, headers: buffer.getvalue())
    result = fetcher.download("owner", "repo", "abcdef1", tmp_path)
    assert result["read_only_source"] is True and Path(result["root"]).exists()


def test_corpus_experiment_and_report(tmp_path: Path):
    make_repo(tmp_path)
    corpus = ReproducibleCorpus([CorpusTask("T1", "No-op", "Return no patch", "repo", "abcdef1", ("compile",))])
    def transport(endpoint, headers, payload):
        return {"choices": [{"message": {"content": json.dumps({"patch": patch_value(), "declared_complete": True})}}], "usage": {"prompt_tokens": 10, "completion_tokens": 20}}
    adapter = OpenAICompatibleModelAdapter("fixture", "https://example.invalid", transport=transport)
    result = CorpusExperimentRunner(tmp_path).run(corpus, adapter)
    artifacts = save_scientific_report(tmp_path / "reports", result)
    assert result["summary"]["total"] == 1 and result["summary"]["accepted"] == 1
    assert Path(artifacts["json"]).exists() and Path(artifacts["markdown"]).exists()


def test_v39_api_corpus_and_security(tmp_path: Path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from phigraph.core_v3.api import create_core_v3_router
    (tmp_path / "app.py").write_text('password = "super-secret-password"\n')
    app = FastAPI()
    app.include_router(create_core_v3_router(tmp_path / "data", allow_unauthenticated_dev=True))
    client = TestClient(app)
    corpus = client.post("/v3/code/corpus/validate", json={"tasks": [{"id": "T1", "title": "x", "prompt": "y", "repository": "r", "commit_sha": "abcdef1"}]})
    scan = client.post("/v3/code/security/scan", json={"repository_path": str(tmp_path)})
    assert corpus.status_code == 200 and len(corpus.json()["sha256"]) == 64
    assert scan.status_code == 200 and scan.json()["count"] == 1
