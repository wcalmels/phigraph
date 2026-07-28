from pathlib import Path
import subprocess

from phigraph.core_v3.code_v38 import CommitSnapshotBuilder, RequirementTraceBuilder, StaticModelAdapter, PatchProposal, PatchEvaluator, confidence_interval, benchmark_statistics


def repo(root: Path):
    (root/"src").mkdir(); (root/"src"/"app.py").write_text("def value():\n    return 1\n")
    (root/"tests").mkdir(); (root/"tests"/"test_app.py").write_text("from src.app import value\ndef test_value(): assert value()==1\n")
    subprocess.run(["git","init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git","config","user.email","test@example.com"], cwd=root, check=True)
    subprocess.run(["git","config","user.name","Test"], cwd=root, check=True)
    subprocess.run(["git","add","."], cwd=root, check=True)
    subprocess.run(["git","commit","-m","init"], cwd=root, check=True, capture_output=True)


def test_commit_snapshot_is_bound_to_head(tmp_path: Path):
    repo(tmp_path)
    result=CommitSnapshotBuilder(tmp_path).build()
    assert len(result.commit_sha) >= 7 and result.file_count == 2 and len(result.tree_hash)==64


def test_requirement_trace_graph_validates_links():
    graph=RequirementTraceBuilder().build(issues=[{"number":1,"title":"Bug"}], requirements=[{"id":"R1","text":"Fix"}], files=["src/a.py"], tests=["tests/test_a.py"], pull_requests=[{"number":2,"title":"PR"}], links=[{"source":"issue:1","target":"requirement:R1","relation":"defines"},{"source":"requirement:R1","target":"file:src/a.py","relation":"implemented_by"}])
    assert len(graph.nodes)==5 and len(graph.edges)==2


def test_static_model_adapter_is_deterministic():
    adapter=StaticModelAdapter("small", {"claims":[]})
    a=adapter.propose({"id":"T1"},{"x":1}); b=adapter.propose({"id":"T1"},{"x":1})
    assert a["context_hash"]==b["context_hash"]


def test_patch_evaluator_does_not_modify_source(tmp_path: Path):
    repo(tmp_path)
    patch='''diff --git a/src/app.py b/src/app.py\nindex 7c3ef1a..0000000 100644\n--- a/src/app.py\n+++ b/src/app.py\n@@ -1,2 +1,2 @@\n def value():\n-    return 1\n+    return 2\n'''
    before=(tmp_path/"src"/"app.py").read_text()
    result=PatchEvaluator(tmp_path).evaluate(PatchProposal(patch,"m","T1"), checks=("compile",))
    assert result["applied"] and result["accepted"] and result["real_repository_modified"] is False
    assert (tmp_path/"src"/"app.py").read_text()==before


def test_statistics_include_confidence_intervals():
    ci=confidence_interval([1,2,3])
    assert ci["n"]==3 and ci["lower"] < ci["mean"] < ci["upper"]
    stats=benchmark_statistics([{"delta":{"false_claims_accepted_reduction":1},"cost_usd":.1,"latency_ms":10},{"delta":{"false_claims_accepted_reduction":0},"cost_usd":.2,"latency_ms":20}])
    assert stats["cost_usd"]["n"]==2
