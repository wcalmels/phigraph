from __future__ import annotations

from phigraph.hav.adapters import repository_state
from phigraph.hav.connectors.base import BaseStateConnector, ConnectorResult


class CodeRepositoryConnector(BaseStateConnector):
    connector_id = "code-repository-v1"
    def __init__(self, *, tests_passed: int, tests_total: int, ci_status: str, codeql_status: str, package_status: str, docker_status: str, release_gate_status: str, source_system: str = "github-actions") -> None:
        self.tests_passed = tests_passed
        self.tests_total = tests_total
        self.ci_status = ci_status
        self.codeql_status = codeql_status
        self.package_status = package_status
        self.docker_status = docker_status
        self.release_gate_status = release_gate_status
        self.source_system = source_system
    def collect(self) -> ConnectorResult:
        return ConnectorResult(
            state=repository_state(
                tests_passed=self.tests_passed,
                tests_total=self.tests_total,
                ci_status=self.ci_status,
                codeql_status=self.codeql_status,
                package_status=self.package_status,
                docker_status=self.docker_status,
                release_gate_status=self.release_gate_status,
                source_system=self.source_system,
            ),
            connector_id=self.connector_id,
            diagnostics=("repository state normalized",),
        )
