from __future__ import annotations

import hashlib
import json
import math
import shutil
import statistics
import subprocess
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Protocol, Iterable

from .code_benchmark import RepositoryIndexer


@dataclass(frozen=True)
class CommitSnapshot:
    repository: str
    commit_sha: str
    root: str
    tree_hash: str
    file_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CommitSnapshotBuilder:
    """Build a deterministic snapshot bound to a local git commit without mutating the repo."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def build(self, commit_sha: str | None = None) -> CommitSnapshot:
        if not self.root.exists():
            raise FileNotFoundError(self.root)
        sha = commit_sha or self._git("rev-parse", "HEAD")
        snapshot = RepositoryIndexer(self.root).build()
        rows = [(f.path, f.sha256) for f in snapshot.facts]
        tree_hash = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
        remote = self._git_optional("config", "--get", "remote.origin.url") or str(self.root)
        return CommitSnapshot(remote, sha, str(self.root), tree_hash, len(snapshot.facts), {"python_files": len(snapshot.python_files), "test_files": len(snapshot.test_files)})

    def _git(self, *args: str) -> str:
        cp = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=False)
        if cp.returncode != 0:
            raise ValueError(f"git_failed:{cp.stderr.strip()}")
        return cp.stdout.strip()

    def _git_optional(self, *args: str) -> str | None:
        try:
            return self._git(*args)
        except ValueError:
            return None


@dataclass(frozen=True)
class TraceNode:
    id: str
    kind: str
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TraceEdge:
    source: str
    target: str
    relation: str


@dataclass(frozen=True)
class RequirementTraceGraph:
    nodes: tuple[TraceNode, ...]
    edges: tuple[TraceEdge, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [asdict(x) for x in self.nodes], "edges": [asdict(x) for x in self.edges]}


class RequirementTraceBuilder:
    """Create an explicit issue→requirement→file→test→PR trace graph from supplied evidence."""

    def build(self, *, issues: Iterable[dict[str, Any]] = (), requirements: Iterable[dict[str, Any]] = (), files: Iterable[str] = (), tests: Iterable[str] = (), pull_requests: Iterable[dict[str, Any]] = (), links: Iterable[dict[str, str]] = ()) -> RequirementTraceGraph:
        nodes: dict[str, TraceNode] = {}
        def add(identifier: str, kind: str, label: str, metadata: dict[str, Any] | None = None) -> None:
            nodes[identifier] = TraceNode(identifier, kind, label, metadata or {})
        for x in issues: add(f"issue:{x['number']}", "issue", x.get("title", ""), x)
        for x in requirements: add(f"requirement:{x['id']}", "requirement", x.get("text", ""), x)
        for x in files: add(f"file:{x}", "file", x)
        for x in tests: add(f"test:{x}", "test", x)
        for x in pull_requests: add(f"pr:{x['number']}", "pull_request", x.get("title", ""), x)
        edges = []
        for link in links:
            if link["source"] not in nodes or link["target"] not in nodes:
                raise ValueError("trace_link_references_unknown_node")
            edges.append(TraceEdge(link["source"], link["target"], link["relation"]))
        return RequirementTraceGraph(tuple(nodes.values()), tuple(edges))


class ModelAdapter(Protocol):
    name: str
    def propose(self, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class StaticModelAdapter:
    name: str
    response: dict[str, Any]

    def propose(self, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {**self.response, "model": self.name, "task_id": task.get("id"), "context_hash": hashlib.sha256(json.dumps(context, sort_keys=True, default=str).encode()).hexdigest()}


@dataclass(frozen=True)
class PatchProposal:
    patch: str
    model: str
    task_id: str


class PatchEvaluator:
    """Evaluate a unified diff in an isolated temporary copy; never mutates the source repository."""

    def __init__(self, root: str | Path, *, timeout_seconds: int = 120):
        self.root = Path(root).resolve()
        self.timeout_seconds = timeout_seconds

    def evaluate(self, proposal: PatchProposal, checks: tuple[str, ...] = ("compile", "tests")) -> dict[str, Any]:
        if not proposal.patch.strip():
            return {"applied": False, "accepted": False, "reason": "empty_patch", "real_repository_modified": False}
        with tempfile.TemporaryDirectory(prefix="phigraph-patch-") as temp:
            target = Path(temp) / "repo"
            shutil.copytree(self.root, target, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache"))
            patch_file = Path(temp) / "proposal.patch"
            patch_file.write_text(proposal.patch, encoding="utf-8")
            cp = subprocess.run(["git", "apply", "--whitespace=nowarn", str(patch_file)], cwd=target, capture_output=True, text=True, check=False)
            if cp.returncode != 0:
                return {"applied": False, "accepted": False, "reason": "patch_apply_failed", "stderr": cp.stderr[-4000:], "real_repository_modified": False}
            from .code_benchmark import CodeVerifier
            results = [CodeVerifier(target, timeout_seconds=self.timeout_seconds).run(x).to_dict() for x in checks]
            return {"applied": True, "accepted": all(x["passed"] for x in results), "checks": results, "model": proposal.model, "task_id": proposal.task_id, "real_repository_modified": False}


def confidence_interval(values: Iterable[float], confidence: float = 0.95) -> dict[str, float | int]:
    rows = [float(x) for x in values]
    if not rows:
        return {"n": 0, "mean": 0.0, "lower": 0.0, "upper": 0.0}
    mean = statistics.fmean(rows)
    if len(rows) == 1:
        return {"n": 1, "mean": mean, "lower": mean, "upper": mean}
    sd = statistics.stdev(rows)
    # Normal approximation; explicit and deterministic for benchmark summaries.
    z = 1.959963984540054 if confidence == 0.95 else 1.959963984540054
    margin = z * sd / math.sqrt(len(rows))
    return {"n": len(rows), "mean": mean, "lower": mean - margin, "upper": mean + margin}


def benchmark_statistics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = list(rows)
    reductions = [float(x.get("delta", {}).get("false_claims_accepted_reduction", 0)) for x in data]
    costs = [float(x.get("cost_usd", 0)) for x in data]
    latency = [float(x.get("latency_ms", 0)) for x in data]
    return {"false_claim_reduction": confidence_interval(reductions), "cost_usd": confidence_interval(costs), "latency_ms": confidence_interval(latency)}
