"""Static and subprocess tests for the Windows G14 live runner."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "deploy" / "railway_g14_live_runner.ps1"
WRAPPER = ROOT / "scripts" / "deploy" / "railway_g14_backup_restore.ps1"
PINNED_COMMIT = "e805f969421fc0392632365df998d0a248fc9d97"
RAILWAY_PROJECT_ID = "005d1dea-1c82-413c-9aa3-49e8eaeb9709"
RAILWAY_ENVIRONMENT = "production"
RAILWAY_SERVICE = "Postgres"
RUNBOOK = ROOT / "docs" / "operations" / "G14_BACKUP_RESTORE_RUNBOOK.md"
RAILWAY_STUB_SENTINEL = "G14_RAILWAY_STUB_INVOKED"
G14_EXIT_OK = 0
G14_EXIT_PRECONDITION = 2
G14_EXIT_CONFLICT = 3
G14_EXIT_VERIFY_FAIL = 4
WINDOWS_PS51 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
FORBIDDEN_INVOCATIONS = (
    "powershell -Command",
    "pwsh -Command",
    "python -c",
    "py -3 -c",
    "cmd /c",
    "cmd.exe /c",
)
FORBIDDEN_SECRET_APIS = (
    "ConvertFrom-SecureString",
    "Set-Clipboard",
    "Out-File",
    "Add-Content",
    "Start-Transcript",
    "[Console]::Out",
    "Console.Out",
)

_FUNCTION_RE = re.compile(
    r"function (?P<name>[\w-]+) \{",
    re.MULTILINE,
)


def _powershell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell runtime unavailable")
    return shell


def _windows_powershell_51() -> str:
    if not WINDOWS_PS51.is_file():
        pytest.skip("Windows PowerShell 5.1 unavailable")
    return str(WINDOWS_PS51)


def _runner_text() -> str:
    return RUNNER.read_text(encoding="utf-8")


def _extract_function(text: str, function_name: str) -> str:
    marker = f"function {function_name} {{"
    start = text.index(marker)
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"unterminated function: {function_name}")


def _run_runner(*extra: str, env: dict[str, str] | None = None, stdin: str | None = "") -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    for key in (
        "DATABASE_PUBLIC_URL",
        "PHIGRAPH_POSTGRES_DSN",
        "PHIGRAPH_G14_RESTORE_DSN",
        "PGPASSWORD",
        "DATABASE_URL",
    ):
        merged.pop(key, None)
    if env:
        merged.update(env)
    argv = [
        _powershell(),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(RUNNER),
        *extra,
    ]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        env=merged,
        input=stdin,
        cwd=str(ROOT),
    )


def _combined(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout}\n{result.stderr}"


def _assert_no_secrets(result: subprocess.CompletedProcess[str]) -> None:
    combined = _combined(result)
    assert "postgresql://" not in combined
    assert "DATABASE_PUBLIC_URL=" not in combined
    assert "PHIGRAPH_POSTGRES_DSN=" not in combined
    assert "PHIGRAPH_G14_RESTORE_DSN=" not in combined
    assert "PGPASSWORD=" not in combined
    assert "super-secret" not in combined
    assert "should-never-leak" not in combined


def _runner_env_with_railway_sentinel(stub_dir: Path) -> dict[str, str]:
    merged = os.environ.copy()
    for key in (
        "DATABASE_PUBLIC_URL",
        "PHIGRAPH_POSTGRES_DSN",
        "PHIGRAPH_G14_RESTORE_DSN",
        "PGPASSWORD",
        "DATABASE_URL",
    ):
        merged.pop(key, None)
    stub_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        stub = (
            f"@echo off\r\n"
            f"echo {RAILWAY_STUB_SENTINEL}=1 1>&2\r\n"
            "exit /b 99\r\n"
        )
        (stub_dir / "railway.cmd").write_text(stub, encoding="ascii")
        (stub_dir / "railway.bat").write_text(stub, encoding="ascii")
    else:
        stub_path = stub_dir / "railway"
        stub_path.write_text(
            f"#!/bin/sh\necho {RAILWAY_STUB_SENTINEL}=1 >&2\nexit 99\n",
            encoding="ascii",
        )
        stub_path.chmod(0o755)
    merged["PATH"] = str(stub_dir) + os.pathsep + merged.get("PATH", "")
    return merged


def _assert_railway_stub_not_invoked(result: subprocess.CompletedProcess[str]) -> None:
    assert RAILWAY_STUB_SENTINEL not in _combined(result)


def test_runner_file_exists():
    assert RUNNER.is_file()


def test_powershell_parser_accepts_runner():
    shell = _powershell()
    script = (
        "$errors = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{RUNNER.as_posix()}', [ref]$null, [ref]$errors); "
        "if ($errors -and $errors.Count) { $errors | ForEach-Object { $_.ToString() }; exit 1 }; "
        "'PARSE_OK'"
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "PARSE_OK" in result.stdout


def _railway_child_block() -> str:
    text = _runner_text()
    return text[text.index("$childArgs = @(") : text.index("& railway @childArgs")]


def test_child_uses_file_not_command():
    text = _runner_text()
    railway_block = _railway_child_block()
    assert "-File" in railway_block
    assert "$PSCommandPath" in railway_block
    assert "-InsideRailwayEnvironment" in railway_block
    assert "-Command" not in railway_block
    for needle in FORBIDDEN_INVOCATIONS:
        assert needle not in text


def test_child_argv_has_no_dsn():
    text = _runner_text()
    railway_block = _railway_child_block()
    assert "PHIGRAPH_" not in railway_block
    assert "DATABASE_PUBLIC_URL" not in railway_block
    assert "$encoded" not in railway_block
    assert "$plain" not in railway_block
    assert "postgresql://" not in railway_block
    assert "@childArgs" in text
    assert "& railway @childArgs" in text


def test_child_selects_explicit_railway_target_before_double_dash():
    text = _runner_text()
    railway_block = _railway_child_block()
    project_idx = railway_block.index("'--project'")
    environment_idx = railway_block.index("'--environment'")
    service_idx = railway_block.index("'--service'")
    separator_idx = railway_block.index("'--'")
    assert project_idx < environment_idx < service_idx < separator_idx
    assert f"$script:RailwayProjectId = '{RAILWAY_PROJECT_ID}'" in text
    assert RAILWAY_PROJECT_ID
    assert f"$script:RailwayEnvironment = '{RAILWAY_ENVIRONMENT}'" in text
    assert f"$script:RailwayService = '{RAILWAY_SERVICE}'" in text
    assert "'--project', $script:RailwayProjectId" in railway_block
    assert "'--environment', $script:RailwayEnvironment" in railway_block
    assert "'--service', $script:RailwayService" in railway_block


def test_runner_and_runbook_do_not_use_directory_association_workarounds():
    runner = _runner_text()
    runbook = RUNBOOK.read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    exclude = ROOT / ".git" / "info" / "exclude"
    exclude_text = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    for haystack in (runner, runbook):
        assert "railway link" not in haystack
        assert "railway.exe link" not in haystack
    assert "railway link" not in gitignore
    assert ".railway" not in gitignore
    assert "railway link" not in exclude_text
    assert ".railway" not in exclude_text
    assert "OneDrive" not in runner


def test_railway_target_is_not_overridable_via_runner_parameters(tmp_path):
    text = _runner_text()
    param_block = text[text.index("param(") : text.index("Set-StrictMode")]
    for forbidden in (
        r"\$Project\b",
        r"\$Environment\b",
        r"\$Service\b",
        r"\$RailwayProjectId\b",
        r"\$RailwayEnvironment\b",
        r"\$RailwayService\b",
    ):
        assert re.search(forbidden, param_block) is None, forbidden
    assert "$InsideRailwayEnvironment" in param_block
    assert "$ExpectedBaselineCommit" in param_block
    env = _runner_env_with_railway_sentinel(tmp_path / "railway-stub")
    for extra in (
        ("-Project", "00000000-0000-0000-0000-000000000000"),
        ("-Environment", "staging"),
        ("-Service", "phigraph-api"),
        ("-RailwayProjectId", "00000000-0000-0000-0000-000000000000"),
    ):
        result = _run_runner(*extra, env=env)
        assert result.returncode != 0
        _assert_railway_stub_not_invoked(result)
        _assert_no_secrets(result)


def test_inner_source_comes_from_database_public_url_only():
    inner = _extract_function(_runner_text(), "Invoke-G14InsideRailwayEnvironment")
    assert "GetEnvironmentVariable('DATABASE_PUBLIC_URL')" in inner
    assert "Add-G14SslModeRequire" in inner
    assert "$env:PHIGRAPH_POSTGRES_DSN = $sourceDsn" in inner
    assert "Read-Host" not in inner
    assert "GetEnvironmentVariable('PHIGRAPH_POSTGRES_DSN')" not in inner


def test_sslmode_require_preserves_existing_query():
    text = _runner_text()
    helpers = "\n".join(
        [
            _extract_function(text, "Stop-G14FailClosed"),
            _extract_function(text, "Add-G14SslModeRequire"),
        ]
    )
    probe = r"""
$cases = @(
    @{ In = 'postgresql://u:p@h:5432/db'; Out = 'postgresql://u:p@h:5432/db?sslmode=require' },
    @{ In = 'postgresql://u:p@h:5432/db?connect_timeout=5'; Out = 'postgresql://u:p@h:5432/db?connect_timeout=5&sslmode=require' },
    @{ In = 'postgresql://u:p@h:5432/db?sslmode=prefer&connect_timeout=5'; Out = 'postgresql://u:p@h:5432/db?sslmode=require&connect_timeout=5' }
)
foreach ($case in $cases) {
    $got = Add-G14SslModeRequire -Dsn $case.In
    if ($got -ne $case.Out) { throw "sslmode mismatch" }
}
'SSLMODE_OK'
"""
    result = subprocess.run(
        [_powershell(), "-NoProfile", "-NonInteractive", "-Command", helpers + "\n" + probe],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "SSLMODE_OK" in result.stdout
    assert "postgresql://u:p@h:5432/db" not in result.stdout.split("SSLMODE_OK")[0]


def test_finally_clears_secrets():
    text = _runner_text()
    local_fn = _extract_function(text, "Invoke-G14OperatorLocal")
    inner_fn = _extract_function(text, "Invoke-G14InsideRailwayEnvironment")
    assert "finally {" in local_fn
    assert "ZeroFreeBSTR" in local_fn
    assert "Remove-Item Env:PHIGRAPH_G14_RESTORE_DSN" in local_fn
    assert "Remove-Item Env:PHIGRAPH_POSTGRES_DSN" in local_fn
    assert "$plain = $null" in local_fn
    assert "$encoded = $null" in local_fn
    assert "finally {" in inner_fn
    assert "Remove-Item Env:PHIGRAPH_POSTGRES_DSN" in inner_fn


def test_exit_code_is_propagated():
    text = _runner_text()
    assert text.count("exit $code") >= 2
    assert "$code = $LASTEXITCODE" in text
    local_fn = _extract_function(text, "Invoke-G14OperatorLocal")
    inner_fn = _extract_function(text, "Invoke-G14InsideRailwayEnvironment")
    assert "exit $code" in local_fn
    assert "exit $code" in inner_fn


def test_wrapper_exits_instead_of_throwing_on_python_failure():
    text = WRAPPER.read_text(encoding="utf-8")
    assert WRAPPER.is_file()
    assert "function Stop-G14FailClosed" in text
    assert "function Complete-G14Python" in text
    assert "Complete-G14Python 'backup'" in text
    assert "Complete-G14Python 'manifest verification'" in text
    assert "Complete-G14Python 'full drill'" in text
    assert "-Code $code" in text
    assert "exit $Code" in text
    assert "throw" not in text
    assert "Stop-G14FailClosed 'Python runtime not found'" in text
    assert "Stop-G14FailClosed 'PHIGRAPH_POSTGRES_DSN is required'" in text
    assert "Stop-G14FailClosed 'PHIGRAPH_G14_RESTORE_DSN is required for -FullDrill'" in text
    assert "Stop-G14FailClosed 'Specify -BackupOnly, -VerifyManifest, or -FullDrill'" in text
    assert "[Parameter(Mandatory = $true, ParameterSetName = 'VerifyManifest')]" in text
    assert "[string]$ManifestPath" in text


def test_noninteractive_fails_before_requesting_secrets():
    result = _run_runner()
    assert result.returncode == 2
    combined = _combined(result)
    assert "interactive PowerShell console is required" in combined
    assert "Local PostgreSQL" not in combined
    assert "password" not in combined.lower()
    _assert_no_secrets(result)


def test_inner_mode_requires_public_url():
    result = _run_runner("-InsideRailwayEnvironment")
    assert result.returncode == 2
    assert "DATABASE_PUBLIC_URL is required" in _combined(result)
    _assert_no_secrets(result)


def test_inner_mode_rejects_remote_restore_host():
    result = _run_runner(
        "-InsideRailwayEnvironment",
        env={
            "DATABASE_PUBLIC_URL": "postgresql://src:should-never-leak@db.example.invalid:5432/prod",
            "PHIGRAPH_G14_RESTORE_DSN": "postgresql://u:super-secret@db.example.invalid:5432/postgres",
        },
    )
    assert result.returncode == 2
    assert "restore host is not localhost" in _combined(result)
    _assert_no_secrets(result)


def test_inner_mode_rejects_identical_source_and_restore():
    result = _run_runner(
        "-InsideRailwayEnvironment",
        env={
            "DATABASE_PUBLIC_URL": "postgresql://postgres:should-never-leak@127.0.0.1:5432/postgres",
            "PHIGRAPH_G14_RESTORE_DSN": "postgresql://postgres:should-never-leak@127.0.0.1:5432/postgres",
        },
    )
    assert result.returncode == 2
    assert "source and restore DSN must differ" in _combined(result)
    _assert_no_secrets(result)


def test_runner_does_not_invoke_railway_or_postgres_in_fail_closed_paths():
    text = _runner_text()
    inner = _extract_function(text, "Invoke-G14InsideRailwayEnvironment")
    assert "& railway" not in inner
    assert "psycopg" not in text
    result = _run_runner("-InsideRailwayEnvironment")
    assert result.returncode == 2
    _assert_no_secrets(result)


def test_no_secret_persistence_apis():
    text = _runner_text()
    for needle in FORBIDDEN_SECRET_APIS:
        assert needle not in text
    assert "Write-Host $" not in text
    assert "Set-Content" not in text
    assert PINNED_COMMIT in text
    assert "ExpectedBaselineCommit" in text
    assert "ExpectedGitCommit" not in text
    names = _FUNCTION_RE.findall(text)
    assert "Invoke-G14OperatorLocal" in names
    assert "Invoke-G14InsideRailwayEnvironment" in names
    assert "Assert-G14BaselineAndWorktree" in names


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "G14 Test"
    env["GIT_AUTHOR_EMAIL"] = "g14-test@example.invalid"
    env["GIT_COMMITTER_NAME"] = "G14 Test"
    env["GIT_COMMITTER_EMAIL"] = "g14-test@example.invalid"
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
        env=env,
    )


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init")
    _git(path, "config", "user.name", "G14 Test")
    _git(path, "config", "user.email", "g14-test@example.invalid")
    _git(path, "config", "commit.gpgsign", "false")


def _empty_commit(path: Path, message: str) -> str:
    _git(path, "commit", "--allow-empty", "-m", message)
    return _git(path, "rev-parse", "HEAD").stdout.strip()


def _run_baseline_assert(repo: Path, baseline: str) -> subprocess.CompletedProcess[str]:
    text = _runner_text()
    helpers = "\n".join(
        [
            _extract_function(text, "Stop-G14FailClosed"),
            _extract_function(text, "Assert-G14BaselineAndWorktree"),
        ]
    )
    repo_ps = str(repo).replace("'", "''")
    probe = (
        f"Assert-G14BaselineAndWorktree -RepoRoot '{repo_ps}' -BaselineCommit '{baseline}'; "
        "'BASELINE_OK'"
    )
    return subprocess.run(
        [_powershell(), "-NoProfile", "-NonInteractive", "-Command", helpers + "\n" + probe],
        capture_output=True,
        text=True,
        check=False,
    )


def test_operator_mode_uses_ancestor_baseline_not_exact_head():
    text = _runner_text()
    local_fn = _extract_function(text, "Invoke-G14OperatorLocal")
    assert "Assert-G14BaselineAndWorktree" in local_fn
    assert "merge-base --is-ancestor" in text
    assert "status --porcelain" in text
    assert "-ne $ExpectedGitCommit" not in text
    assert "does not match the pinned G14 pilot commit" not in text


def test_baseline_assert_accepts_clean_descendant(tmp_path):
    repo = tmp_path / "descendant"
    _init_git_repo(repo)
    baseline = _empty_commit(repo, "baseline")
    child = _empty_commit(repo, "runner-fix")
    assert child != baseline
    result = _run_baseline_assert(repo, baseline)
    assert result.returncode == 0, result.stderr or result.stdout
    assert "BASELINE_OK" in result.stdout


def test_baseline_assert_rejects_unrelated_history(tmp_path):
    baseline_repo = tmp_path / "baseline"
    other_repo = tmp_path / "other"
    _init_git_repo(baseline_repo)
    baseline = _empty_commit(baseline_repo, "railway-baseline")
    _init_git_repo(other_repo)
    _empty_commit(other_repo, "unrelated")
    result = _run_baseline_assert(other_repo, baseline)
    assert result.returncode == 2
    assert "HEAD does not descend from the G14 Railway baseline commit" in _combined(result)
    assert "BASELINE_OK" not in result.stdout


def test_baseline_assert_rejects_dirty_worktree(tmp_path):
    repo = tmp_path / "dirty"
    _init_git_repo(repo)
    baseline = _empty_commit(repo, "baseline")
    _empty_commit(repo, "runner-fix")
    (repo / "scratch.txt").write_text("dirty", encoding="utf-8")
    result = _run_baseline_assert(repo, baseline)
    assert result.returncode == 2
    assert "worktree is not clean" in _combined(result)
    assert "BASELINE_OK" not in result.stdout


def _wrapper_env(tmp_path: Path, stub_exit: int | None = None) -> dict[str, str]:
    merged = os.environ.copy()
    for key in (
        "PHIGRAPH_POSTGRES_DSN",
        "PHIGRAPH_G14_RESTORE_DSN",
        "PGPASSWORD",
        "DATABASE_URL",
        "DATABASE_PUBLIC_URL",
    ):
        merged.pop(key, None)
    merged["PHIGRAPH_POSTGRES_DSN"] = "postgresql://g14:stub-pass@127.0.0.1:5432/g14_stub"
    merged["G14_TEST_WRAPPER"] = str(WRAPPER)
    if stub_exit is not None:
        stub_dir = tmp_path / "py-stub"
        stub_dir.mkdir(parents=True, exist_ok=True)
        stub = f"@echo off\r\nexit /b {int(stub_exit)}\r\n"
        for name in ("py.cmd", "python.cmd", "python3.cmd"):
            (stub_dir / name).write_text(stub, encoding="ascii")
        merged["PATH"] = str(stub_dir) + os.pathsep + merged.get("PATH", "")
    return merged


def _run_ps51_file(
    script: Path,
    extra: list[str] | None = None,
    *,
    env: dict[str, str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [
        _windows_powershell_51(),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *(extra or []),
    ]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(cwd or ROOT),
        input="",
    )


def _run_wrapper(tmp_path: Path, extra: list[str], *, stub_exit: int | None = None) -> subprocess.CompletedProcess[str]:
    return _run_ps51_file(WRAPPER, extra, env=_wrapper_env(tmp_path, stub_exit), cwd=tmp_path)


def test_wrapper_local_precondition_uses_exit_2(tmp_path):
    result = _run_wrapper(
        tmp_path,
        ["-FullDrill", "-ConfirmIsolatedRestore", "WRONG-TOKEN", "-ArtifactDir", str(tmp_path / "artifacts")],
        stub_exit=0,
    )
    assert result.returncode == G14_EXIT_PRECONDITION
    assert "G14-ISOLATED-RESTORE is required for -FullDrill" in _combined(result)
    _assert_no_secrets(result)


@pytest.mark.parametrize(
    "stub_exit",
    [G14_EXIT_OK, G14_EXIT_PRECONDITION, G14_EXIT_CONFLICT, G14_EXIT_VERIFY_FAIL],
)
def test_wrapper_preserves_python_exit_codes_on_powershell_51(tmp_path, stub_exit):
    artifacts = tmp_path / "artifacts"
    result = _run_wrapper(
        tmp_path,
        ["-BackupOnly", "-ArtifactDir", str(artifacts)],
        stub_exit=stub_exit,
    )
    assert result.returncode == stub_exit
    if stub_exit == G14_EXIT_OK:
        assert "G14 backup complete" in _combined(result)
    else:
        assert f"G14 backup failed (exit {stub_exit})" in _combined(result)
        assert result.returncode != 1
    _assert_no_secrets(result)


@pytest.mark.parametrize(
    "stub_exit",
    [G14_EXIT_OK, G14_EXIT_PRECONDITION, G14_EXIT_CONFLICT, G14_EXIT_VERIFY_FAIL],
)
def test_live_runner_parent_forwards_wrapper_exit_codes_on_powershell_51(tmp_path, stub_exit):
    artifacts = tmp_path / "artifacts"
    parent = tmp_path / "parent_forward.ps1"
    parent.write_text(
        "\n".join(
            [
                "Set-StrictMode -Version Latest",
                "$ErrorActionPreference = 'Stop'",
                "& $env:G14_TEST_WRAPPER -BackupOnly -ArtifactDir $env:G14_TEST_ARTIFACT",
                "$code = $LASTEXITCODE",
                "if ($null -eq $code) { $code = 0 }",
                "exit $code",
                "",
            ]
        ),
        encoding="ascii",
    )
    env = _wrapper_env(tmp_path, stub_exit)
    env["G14_TEST_ARTIFACT"] = str(artifacts)
    result = _run_ps51_file(parent, env=env, cwd=tmp_path)
    assert result.returncode == stub_exit
    _assert_no_secrets(result)
