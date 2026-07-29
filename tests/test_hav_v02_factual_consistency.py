from phigraph.hav.extraction import FactualClaimExtractor
from phigraph.hav.verification_v2 import MultiOutputConsistencyChecker


def test_factual_candidates_are_extracted_without_claiming_truth():
    claims = FactualClaimExtractor().extract("Coverage 82.5% in 2026 with 117 tests.")
    assert {"percentage","date","quantity"} <= {c.claim_type for c in claims}
    assert all(c.requires_external_grounding for c in claims)

def test_consistency_is_auxiliary_and_detects_status_conflict():
    result = MultiOutputConsistencyChecker().assess(["CI passed", "CI failed"])
    assert result.conflicting_status_terms == ("failed","passed")
    assert "not proof of truth" in result.note
