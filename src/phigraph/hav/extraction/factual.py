from __future__ import annotations

import re
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedFactualClaim:
    claim_id: str
    text: str
    claim_type: str
    normalized_value: str
    confidence: float
    requires_external_grounding: bool = True

class FactualClaimExtractor:
    _patterns = (
        ("percentage", re.compile(r"\b\d+(?:\.\d+)?\s*%")),
        ("date", re.compile(r"\b(?:19|20)\d{2}(?:-\d{2}-\d{2})?\b")),
        ("quantity", re.compile(r"\b\d+(?:\.\d+)?\s+(?:users?|tests?|servers?|GB|MB|ms|seconds?|hours?)\b", re.I)),
        ("attribution", re.compile(r"(?i)\b(?:according to|según)\s+[^,.]{3,80}")),
    )
    def extract(self, text: str) -> list[ExtractedFactualClaim]:
        output, seen = [], set()
        for claim_type, pattern in self._patterns:
            for match in pattern.finditer(text):
                raw = match.group(0).strip()
                key = (claim_type, raw.lower())
                if key in seen:
                    continue
                seen.add(key)
                output.append(ExtractedFactualClaim(
                    claim_id=f"fact_{uuid.uuid4().hex}",
                    text=raw,
                    claim_type=claim_type,
                    normalized_value=raw.lower(),
                    confidence=0.8,
                ))
        return output
