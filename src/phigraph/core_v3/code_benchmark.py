from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class RepositoryFact:
    path: str
    kind: str
    sha256: str
    size: int
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepositorySnapshot:
    root: str
    facts: tuple[RepositoryFact, ...]
    test_files: tuple[str, ...]
    python_files: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "facts": [asdict(x) for x in self.facts],
            "test_files": list(self.test_files),
            "python_files": list(self.python_files),
            "metadata": self.metadata,
        }


class RepositoryIndexer:
    """Build a deterministic, minimal repository graph input for PhiGraph Code."""

    def __init__(self, root: str | Path, *, max_file_bytes: int = 1_000_000):
        self.root = Path(root).resolve()
        self.max_file_bytes = max_file_bytes

    def build(self) -> RepositorySnapshot:
        if not self.root.exists():
            raise FileNotFoundError(self.root)
        facts: list[RepositoryFact] = []
        python_files: list[str] = []
        test_files: list[str] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or any(part in {".git", ".venv", "__pycache__", ".pytest_cache"} for part in path.parts):
                continue
            rel = path.relative_to(self.root).as_posix()
            size = path.stat().st_size
            if size > self.max_file_bytes:
                continue
            data = path.read_bytes()
            symbols: tuple[str, ...] = ()
            kind = path.suffix.lower().lstrip(".") or "file"
            if path.suffix == ".py":
                python_files.append(rel)
                if path.name.startswith("test_") or "/tests/" in f"/{rel}":
                    test_files.append(rel)
                try:
                    tree = ast.parse(data.decode("utf-8"))
                    symbols = tuple(sorted({n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}))
                except (SyntaxError, UnicodeDecodeError):
                    symbols = ()
            facts.append(RepositoryFact(rel, kind, hashlib.sha256(data).hexdigest(), size, symbols))
        return RepositorySnapshot(str(self.root), tuple(facts), tuple(test_files), tuple(python_files), {"file_count": len(facts)})


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    exit_code: int
    duration_ms: float
    stdout: str
    stderr: str
    command: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CodeVerifier:
    """Deterministic verifier with an allow-listed command surface."""

    ALLOWED = {"compile", "tests", "lint", "typecheck"}

    def __init__(self, root: str | Path, *, timeout_seconds: int = 120):
        self.root = Path(root).resolve()
        self.timeout_seconds = timeout_seconds

    def run(self, check: str) -> CheckResult:
        if check not in self.ALLOWED:
            raise ValueError(f"unsupported_check:{check}")
        command = self._command(check)
        started = time.perf_counter()
        completed = subprocess.run(command, cwd=self.root, capture_output=True, text=True, timeout=self.timeout_seconds, check=False)
        return CheckResult(
            check,
            completed.returncode == 0,
            completed.returncode,
            round((time.perf_counter() - started) * 1000, 3),
            completed.stdout[-20_000:],
            completed.stderr[-20_000:],
            tuple(command),
        )

    def _command(self, check: str) -> list[str]:
        if check == "compile":
            return [sys.executable, "-m", "compileall", "-q", "src"]
        if check == "tests":
            return [sys.executable, "-m", "pytest", "-q"]
        if check == "lint":
            return [sys.executable, "-m", "ruff", "check", "."]
        return [sys.executable, "-m", "mypy", "src"]


@dataclass(frozen=True)
class AgentReport:
    agent: str
    claims: tuple[dict[str, Any], ...]
    declared_complete: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkResult:
    mode: str
    accepted_claims: int
    rejected_claims: int
    unverified_claims: int
    false_claims_accepted: int
    task_accepted_complete: bool
    checks: tuple[CheckResult, ...]
    details: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = [x.to_dict() for x in self.checks]
        return data


class PhiGraphCodeBenchmark:
    """Compare naive acceptance with evidence-gated PhiGraph acceptance."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.verifier = CodeVerifier(self.root)

    def evaluate(self, report: AgentReport, *, governed: bool, run_checks: Iterable[str] = ("compile", "tests")) -> BenchmarkResult:
        checks = tuple(self.verifier.run(name) for name in run_checks) if governed else ()
        check_map = {x.name: x for x in checks}
        accepted = rejected = unverified = false_accepted = 0
        details: list[dict[str, Any]] = []
        for claim in report.claims:
            required = claim.get("requires_check")
            asserted = bool(claim.get("asserted", True))
            actual = claim.get("actual")
            if not governed:
                status = "accepted"
            elif required:
                check = check_map.get(str(required))
                status = "accepted" if check and check.passed else "rejected"
            elif "actual" in claim:
                status = "accepted" if asserted == bool(actual) else "rejected"
            else:
                status = "unverified"
            if status == "accepted":
                accepted += 1
                if actual is False or (required and required in check_map and not check_map[required].passed):
                    false_accepted += 1
            elif status == "rejected":
                rejected += 1
            else:
                unverified += 1
            details.append({"claim": claim, "status": status})
        complete = report.declared_complete if not governed else report.declared_complete and all(x.passed for x in checks) and rejected == 0 and unverified == 0
        return BenchmarkResult("governed" if governed else "baseline", accepted, rejected, unverified, false_accepted, complete, checks, tuple(details))

    def compare(self, report: AgentReport) -> dict[str, Any]:
        baseline = self.evaluate(report, governed=False)
        governed = self.evaluate(report, governed=True)
        return {
            "baseline": baseline.to_dict(),
            "governed": governed.to_dict(),
            "delta": {
                "false_claims_accepted_reduction": baseline.false_claims_accepted - governed.false_claims_accepted,
                "completion_blocked": baseline.task_accepted_complete and not governed.task_accepted_complete,
            },
        }


@dataclass(frozen=True)
class GitHubRepositoryDescriptor:
    owner: str
    repository: str
    default_branch: str = "main"
    commit_sha: str | None = None

    @property
    def canonical_id(self) -> str:
        suffix = f"@{self.commit_sha}" if self.commit_sha else f"@{self.default_branch}"
        return f"github:{self.owner}/{self.repository}{suffix}"

    def to_context(self) -> dict[str, Any]:
        return {"provider": "github", "owner": self.owner, "repository": self.repository, "default_branch": self.default_branch, "commit_sha": self.commit_sha, "canonical_id": self.canonical_id}


def save_benchmark(path: str | Path, result: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

@dataclass(frozen=True)
class ModelRun:
    model: str
    report: AgentReport
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class MultiModelBenchmarkSuite:
    """Evaluate multiple agent/model reports against the same repository evidence."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def run(self, runs: Iterable[ModelRun]) -> dict[str, Any]:
        results = []
        for run in runs:
            comparison = PhiGraphCodeBenchmark(self.root).compare(run.report)
            results.append({"model": run.model, "cost_usd": run.cost_usd, "latency_ms": run.latency_ms, **comparison})
        return {
            "repository": str(self.root),
            "runs": results,
            "summary": {
                "models": len(results),
                "baseline_false_claims": sum(x["baseline"]["false_claims_accepted"] for x in results),
                "governed_false_claims": sum(x["governed"]["false_claims_accepted"] for x in results),
                "completion_blocks": sum(1 for x in results if x["delta"]["completion_blocked"]),
                "total_cost_usd": round(sum(float(x["cost_usd"]) for x in results), 6),
                "total_latency_ms": round(sum(float(x["latency_ms"]) for x in results), 3),
            },
        }


def benchmark_markdown(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    lines = ["# PhiGraph Code Benchmark Report", "", f"Repository: `{result.get('repository', '')}`", "", "## Summary", "", f"- Models evaluated: {summary.get('models', 0)}", f"- Baseline false claims accepted: {summary.get('baseline_false_claims', 0)}", f"- Governed false claims accepted: {summary.get('governed_false_claims', 0)}", f"- Incorrect completions blocked: {summary.get('completion_blocks', 0)}", f"- Total reported cost: USD {summary.get('total_cost_usd', 0)}", f"- Total reported latency: {summary.get('total_latency_ms', 0)} ms", "", "## Runs", ""]
    for row in result.get("runs", []):
        lines.extend([f"### {row['model']}", f"- Baseline complete: {row['baseline']['task_accepted_complete']}", f"- Governed complete: {row['governed']['task_accepted_complete']}", f"- False claims reduction: {row['delta']['false_claims_accepted_reduction']}", ""])
    return "\n".join(lines)


def save_benchmark_report(directory: str | Path, result: dict[str, Any]) -> dict[str, str]:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "benchmark.json"
    md_path = target / "benchmark.md"
    save_benchmark(json_path, result)
    md_path.write_text(benchmark_markdown(result), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
