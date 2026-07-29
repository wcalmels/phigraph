from __future__ import annotations

from phigraph.hav.models import AuthoritativeState, EvidenceFact


def repository_state(
    *,
    tests_passed: int,
    tests_total: int,
    ci_status: str,
    codeql_status: str,
    package_status: str,
    docker_status: str,
    release_gate_status: str,
    source_system: str = "github-actions",
) -> AuthoritativeState:
    facts = [
        EvidenceFact.create(source=source_system, subject="repository", predicate="tests_passed", value=tests_passed),
        EvidenceFact.create(source=source_system, subject="repository", predicate="tests_total", value=tests_total),
    ]
    for predicate, value in [
        ("ci_status", ci_status),
        ("codeql_status", codeql_status),
        ("package_status", package_status),
        ("docker_status", docker_status),
    ]:
        facts.append(EvidenceFact.create(
            source=source_system,
            subject="repository",
            predicate=predicate,
            value=value,
            metadata={"required": True},
        ))
    facts.append(EvidenceFact.create(
        source=source_system,
        subject="repository",
        predicate="release_gate_status",
        value=release_gate_status,
        metadata={"required": True},
    ))
    return AuthoritativeState.create(source_system=source_system, evidence=facts)
