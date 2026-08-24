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
PINNED_COMMIT = "e805f969421fc0392632365df998d0a248fc9d97"
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


def test_child_uses_file_not_command():
    text = _runner_text()
    railway_block = text[text.index("$childArgs = @(") : text.index("& railway @childArgs")]
    assert "-File" in railway_block
    assert "$PSCommandPath" in railway_block
    assert "-InsideRailwayEnvironment" in railway_block
    assert "-Command" not in railway_block
    for needle in FORBIDDEN_INVOCATIONS:
        assert needle not in text


def test_child_argv_has_no_dsn():
    text = _runner_text()
    railway_block = text[text.index("$childArgs = @(") : text.index("& railway @childArgs")]
    assert "PHIGRAPH_" not in railway_block
    assert "DATABASE_PUBLIC_URL" not in railway_block
    assert "$encoded" not in railway_block
    assert "$plain" not in railway_block
    assert "postgresql://" not in railway_block
    assert "@childArgs" in text
    assert "& railway @childArgs" in text


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
    names = _FUNCTION_RE.findall(text)
    assert "Invoke-G14OperatorLocal" in names
    assert "Invoke-G14InsideRailwayEnvironment" in names
