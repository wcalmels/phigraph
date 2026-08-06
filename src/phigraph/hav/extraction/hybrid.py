from __future__ import annotations

from phigraph.hav.extraction.factual import FactualClaimExtractor
from phigraph.hav.extractor import RuleBasedClaimExtractor
from phigraph.hav.models import Claim


class HybridClaimExtractor:
    def __init__(self) -> None:
        self.structured = RuleBasedClaimExtractor()
        self.factual = FactualClaimExtractor()
    def extract(self, text: str) -> list[Claim]:
        claims = self.structured.extract(text)
        for item in self.factual.extract(text):
            claims.append(Claim.create(
                subject="external_fact",
                predicate=item.claim_type,
                value=item.normalized_value,
                text=item.text,
                critical=False,
                confidence=item.confidence,
                metadata={"requires_external_grounding": True, "factual_claim_id": item.claim_id},
            ))
        return claims
