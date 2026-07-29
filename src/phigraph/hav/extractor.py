from __future__ import annotations

import re

from phigraph.hav.models import Claim


class RuleBasedClaimExtractor:
    _patterns = [
        (
            re.compile(r"(?i)tests?\s+(?:passed|passing|aprobados?)\s*[:=]?\s*(\d+)"),
            "repository", "tests_passed", int, False,
        ),
        (
            re.compile(r"(?i)codeql\s*(?:status)?\s*[:=]?\s*(passed|failed|pending|disabled|aprobado|fallido|pendiente|deshabilitado)"),
            "repository", "codeql_status", str, True,
        ),
        (
            re.compile(r"(?i)coverage\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%"),
            "repository", "coverage_pct", float, False,
        ),
    ]

    _global_success = re.compile(
        r"(?i)\b(all checks passed|everything passed|fully approved|"
        r"todos los controles (?:pasaron|aprobaron)|todo (?:pasó|aprobado)|"
        r"repositorio completamente aprobado)\b"
    )
    _production_ready = re.compile(
        r"(?i)\b(production ready|ready for production|listo para producción|"
        r"apto para producción|deploy ready)\b"
    )

    def extract(self, text: str) -> list[Claim]:
        claims: list[Claim] = []
        for pattern, subject, predicate, caster, critical in self._patterns:
            for match in pattern.finditer(text):
                value = caster(match.group(1))
                if predicate == "codeql_status":
                    value = self._normalize_status(str(value))
                claims.append(Claim.create(
                    subject=subject,
                    predicate=predicate,
                    value=value,
                    text=match.group(0),
                    critical=critical,
                ))
        success_match = self._global_success.search(text)
        if success_match:
            claims.append(Claim.create(
                subject="repository",
                predicate="all_required_checks_passed",
                value=True,
                text=success_match.group(0),
                critical=True,
            ))
        ready_match = self._production_ready.search(text)
        if ready_match:
            claims.append(Claim.create(
                subject="repository",
                predicate="production_ready",
                value=True,
                text=ready_match.group(0),
                critical=True,
            ))
        return claims

    @staticmethod
    def _normalize_status(value: str) -> str:
        return {
            "aprobado": "passed",
            "fallido": "failed",
            "pendiente": "pending",
            "deshabilitado": "disabled",
        }.get(value.lower(), value.lower())
