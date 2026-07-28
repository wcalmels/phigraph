from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from .code_v38 import PatchEvaluator, PatchProposal, benchmark_statistics


@dataclass(frozen=True)
class CorpusTask:
    id: str
    title: str
    prompt: str
    repository: str
    commit_sha: str
    required_checks: tuple[str, ...] = ("compile", "tests")
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_checks"] = list(self.required_checks)
        return data


class ReproducibleCorpus:
    """Versioned JSONL task corpus with a deterministic content hash."""

    def __init__(self, tasks: Iterable[CorpusTask]):
        self.tasks = tuple(tasks)
        ids = [task.id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_corpus_task_id")

    @property
    def sha256(self) -> str:
        payload = json.dumps([task.to_dict() for task in self.tasks], sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {"count": len(self.tasks), "sha256": self.sha256, "tasks": [task.to_dict() for task in self.tasks]}

    def save_jsonl(self, path: str | Path) -> str:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(json.dumps(task.to_dict(), sort_keys=True) for task in self.tasks) + ("\n" if self.tasks else ""), encoding="utf-8")
        return str(target)

    @classmethod
    def load_jsonl(cls, path: str | Path) -> "ReproducibleCorpus":
        tasks = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row["required_checks"] = tuple(row.get("required_checks", ("compile", "tests")))
            tasks.append(CorpusTask(**row))
        return cls(tasks)


@dataclass(frozen=True)
class ModelResponse:
    model: str
    content: dict[str, Any]
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    provider: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderTransport(Protocol):
    def __call__(self, endpoint: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]: ...


class OpenAICompatibleModelAdapter:
    """Provider-neutral adapter for OpenAI-compatible chat endpoints.

    Network behavior is injectable for deterministic tests. The adapter never receives
    repository write credentials and only returns a proposal payload.
    """

    def __init__(
        self,
        model: str,
        endpoint: str,
        *,
        api_key: str | None = None,
        provider: str = "openai-compatible",
        transport: ProviderTransport | None = None,
        input_cost_per_million: float = 0.0,
        output_cost_per_million: float = 0.0,
    ):
        self.model = model
        self.endpoint = endpoint
        self.api_key = api_key
        self.provider = provider
        self.transport = transport or self._transport
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million

    def propose(self, task: dict[str, Any], context: dict[str, Any]) -> ModelResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return JSON with patch, claims, and declared_complete. Do not claim checks were run unless evidence is supplied."},
                {"role": "user", "content": json.dumps({"task": task, "context": context}, sort_keys=True, default=str)},
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        started = time.perf_counter()
        raw = self.transport(self.endpoint, headers, payload)
        latency = round((time.perf_counter() - started) * 1000, 3)
        usage = raw.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        content = self._content(raw)
        cost = (input_tokens * self.input_cost_per_million + output_tokens * self.output_cost_per_million) / 1_000_000
        return ModelResponse(self.model, content, latency, input_tokens, output_tokens, round(cost, 8), self.provider)

    @staticmethod
    def _content(raw: dict[str, Any]) -> dict[str, Any]:
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("invalid_model_response") from exc
        if isinstance(content, dict):
            return content
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("model_response_not_json") from exc
        if not isinstance(parsed, dict):
            raise ValueError("model_response_not_object")
        return parsed

    @staticmethod
    def _transport(endpoint: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode())


@dataclass(frozen=True)
class SecurityFinding:
    rule: str
    severity: str
    path: str
    line: int
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeterministicSecurityScanner:
    """Small deterministic scanner for benchmark gating; not a replacement for SAST."""

    RULES = (
        ("hardcoded-private-key", "critical", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
        ("hardcoded-secret", "high", re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*=\s*['\"][^'\"]{8,}['\"]")),
        ("shell-true", "high", re.compile(r"subprocess\.(?:run|Popen|call)\([^\n]*shell\s*=\s*True")),
        ("unsafe-eval", "high", re.compile(r"\beval\s*\(")),
        ("unsafe-exec", "high", re.compile(r"\bexec\s*\(")),
    )

    def scan(self, root: str | Path) -> list[SecurityFinding]:
        base = Path(root).resolve()
        findings: list[SecurityFinding] = []
        for path in sorted(base.rglob("*")):
            if not path.is_file() or any(x in path.parts for x in (".git", ".venv", "__pycache__")):
                continue
            if path.suffix.lower() not in {".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".env"}:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(lines, 1):
                for rule, severity, pattern in self.RULES:
                    if pattern.search(line):
                        fingerprint = hashlib.sha256(f"{rule}:{path.relative_to(base)}:{number}:{line.strip()}".encode()).hexdigest()[:16]
                        findings.append(SecurityFinding(rule, severity, path.relative_to(base).as_posix(), number, fingerprint))
        return findings

    def scan_patch(self, patch: str) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        current_path = "patch"
        added_line = 0
        for raw in patch.splitlines():
            if raw.startswith("+++ b/"):
                current_path = raw[6:]
                added_line = 0
                continue
            if raw.startswith("@@"):
                match = re.search(r"\+(\d+)", raw)
                added_line = int(match.group(1)) - 1 if match else 0
                continue
            if raw.startswith("+") and not raw.startswith("+++"):
                added_line += 1
                line = raw[1:]
                for rule, severity, pattern in self.RULES:
                    if pattern.search(line):
                        fingerprint = hashlib.sha256(f"{rule}:{current_path}:{added_line}:{line.strip()}".encode()).hexdigest()[:16]
                        findings.append(SecurityFinding(rule, severity, current_path, added_line, fingerprint))
            elif not raw.startswith("-"):
                added_line += 1
        return findings


class DependencyInventory:
    """Deterministically inventories declared Python dependencies without resolving them."""

    def build(self, root: str | Path) -> dict[str, Any]:
        base = Path(root)
        dependencies: set[str] = set()
        pyproject = base / "pyproject.toml"
        requirements = list(base.glob("requirements*.txt"))
        if pyproject.exists():
            text = pyproject.read_text(encoding="utf-8")
            block = re.search(r"(?ms)^dependencies\s*=\s*\[(.*?)^\]", text)
            if block:
                dependencies.update(re.findall(r"['\"]([^'\"]+)['\"]", block.group(1)))
        for path in requirements:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "-")):
                    dependencies.add(line)
        rows = sorted(dependencies)
        digest = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
        return {"count": len(rows), "dependencies": rows, "sha256": digest}


class GitHubCommitArchiveFetcher:
    """Read-only GitHub archive fetcher with safe extraction and injectable bytes fetcher."""

    def __init__(self, token: str | None = None, *, fetcher: Callable[[str, dict[str, str]], bytes] | None = None):
        self.token = token
        self.fetcher = fetcher or self._fetch

    def download(self, owner: str, repository: str, commit_sha: str, destination: str | Path) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repository):
            raise ValueError("invalid_github_repository")
        if not re.fullmatch(r"[0-9A-Fa-f]{7,64}", commit_sha):
            raise ValueError("invalid_commit_sha")
        url = f"https://api.github.com/repos/{owner}/{repository}/tarball/{commit_sha}"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "TUCH-PhiGraph-Core-v3.9"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        payload = self.fetcher(url, headers)
        digest = hashlib.sha256(payload).hexdigest()
        target = Path(destination).resolve()
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                resolved = (target / member.name).resolve()
                if target not in resolved.parents and resolved != target:
                    raise ValueError("unsafe_archive_path")
                if member.issym() or member.islnk():
                    raise ValueError("archive_links_not_allowed")
            archive.extractall(target, members=members, filter="data")
        roots = sorted(x for x in target.iterdir() if x.is_dir())
        return {"owner": owner, "repository": repository, "commit_sha": commit_sha, "archive_sha256": digest, "root": str(roots[0] if len(roots) == 1 else target), "read_only_source": True}

    @staticmethod
    def _fetch(url: str, headers: dict[str, str]) -> bytes:
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()


class PatchQualityEvaluator:
    """Combines isolated patch execution with deterministic quality/security evidence."""

    def __init__(self, root: str | Path, *, timeout_seconds: int = 120):
        self.root = Path(root).resolve()
        self.timeout_seconds = timeout_seconds

    def evaluate(self, proposal: PatchProposal, checks: tuple[str, ...] = ("compile", "tests")) -> dict[str, Any]:
        scanner = DeterministicSecurityScanner()
        base_security = scanner.scan(self.root)
        introduced_security = scanner.scan_patch(proposal.patch)
        base_dependencies = DependencyInventory().build(self.root)
        patch = PatchEvaluator(self.root, timeout_seconds=self.timeout_seconds).evaluate(proposal, checks)
        patch_stats = self._patch_stats(proposal.patch)
        result = {
            **patch,
            "patch_stats": patch_stats,
            "baseline_security_findings": len(base_security),
            "introduced_security_findings": [x.to_dict() for x in introduced_security],
            "baseline_dependency_inventory": base_dependencies,
            "quality_gate": {
                "checks_passed": bool(patch.get("accepted")),
                "patch_size_within_limit": patch_stats["changed_lines"] <= 1000,
                "binary_changes": patch_stats["binary_files"],
                "new_high_or_critical_findings": sum(1 for x in introduced_security if x.severity in {"high", "critical"}),
            },
        }
        result["quality_gate"]["accepted"] = all((result["quality_gate"]["checks_passed"], result["quality_gate"]["patch_size_within_limit"], result["quality_gate"]["binary_changes"] == 0, result["quality_gate"]["new_high_or_critical_findings"] == 0))
        result["accepted"] = bool(result.get("accepted")) and bool(result["quality_gate"]["accepted"])
        return result

    @staticmethod
    def _patch_stats(patch: str) -> dict[str, int]:
        files = set(re.findall(r"^\+\+\+ b/(.+)$", patch, flags=re.MULTILINE))
        added = sum(1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
        deleted = sum(1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))
        binary = len(re.findall(r"^Binary files ", patch, flags=re.MULTILINE))
        return {"files_changed": len(files), "lines_added": added, "lines_deleted": deleted, "changed_lines": added + deleted, "binary_files": binary}


class CorpusExperimentRunner:
    """Runs a model adapter over a reproducible corpus and emits auditable measurements."""

    def __init__(self, repository_root: str | Path):
        self.repository_root = Path(repository_root).resolve()

    def run(self, corpus: ReproducibleCorpus, adapter: OpenAICompatibleModelAdapter, *, repetitions: int = 1) -> dict[str, Any]:
        if repetitions < 1 or repetitions > 100:
            raise ValueError("invalid_repetitions")
        rows: list[dict[str, Any]] = []
        for task in corpus.tasks:
            for repetition in range(repetitions):
                context = {"repository": str(self.repository_root), "commit_sha": task.commit_sha, "corpus_sha256": corpus.sha256}
                response = adapter.propose(task.to_dict(), context)
                patch = str(response.content.get("patch") or "")
                evaluation = PatchQualityEvaluator(self.repository_root).evaluate(PatchProposal(patch, response.model, task.id), task.required_checks)
                rows.append({"task_id": task.id, "repetition": repetition + 1, "model": response.model, "provider": response.provider, "latency_ms": response.latency_ms, "cost_usd": response.cost_usd, "input_tokens": response.input_tokens, "output_tokens": response.output_tokens, "declared_complete": bool(response.content.get("declared_complete")), "evaluation": evaluation})
        accepted = [1.0 if x["evaluation"].get("accepted") else 0.0 for x in rows]
        stats_rows = [{"delta": {"false_claims_accepted_reduction": value}, "cost_usd": row["cost_usd"], "latency_ms": row["latency_ms"]} for row, value in zip(rows, accepted)]
        return {"corpus": corpus.to_dict(), "model": adapter.model, "provider": adapter.provider, "repetitions": repetitions, "runs": rows, "summary": {"total": len(rows), "accepted": int(sum(accepted)), "acceptance_rate": (sum(accepted) / len(rows) if rows else 0.0), "statistics": benchmark_statistics(stats_rows)}}


def scientific_report(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    corpus = result.get("corpus", {})
    stats = summary.get("statistics", {})
    return "\n".join([
        "# PhiGraph Code Scientific Benchmark Report",
        "",
        f"- Corpus SHA-256: `{corpus.get('sha256', '')}`",
        f"- Tasks: {corpus.get('count', 0)}",
        f"- Model: `{result.get('model', '')}`",
        f"- Provider: `{result.get('provider', '')}`",
        f"- Repetitions: {result.get('repetitions', 0)}",
        f"- Total runs: {summary.get('total', 0)}",
        f"- Accepted patches: {summary.get('accepted', 0)}",
        f"- Acceptance rate: {summary.get('acceptance_rate', 0):.4f}",
        "",
        "## Statistical summary",
        "",
        f"- Acceptance proxy mean: {stats.get('false_claim_reduction', {}).get('mean', 0):.4f}",
        f"- Mean cost (USD): {stats.get('cost_usd', {}).get('mean', 0):.8f}",
        f"- Mean latency (ms): {stats.get('latency_ms', {}).get('mean', 0):.3f}",
        "",
        "## Scope",
        "",
        "Results apply only to the declared corpus, commit snapshots, checks, model configuration, and repetitions. They do not establish general model superiority.",
    ])


def save_scientific_report(directory: str | Path, result: dict[str, Any]) -> dict[str, str]:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "experiment.json"
    markdown_path = target / "experiment.md"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(scientific_report(result), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}
