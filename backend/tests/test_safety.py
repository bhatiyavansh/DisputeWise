"""Part G -- response safety policy tests."""

from app.evidence_intel import versions as v
from app.evidence_intel.safety import determine_response_state
from app.evidence_intel.verifier import ClaimVerification


def _cv(claim_id, status):
    return ClaimVerification(claim_id=claim_id, status=status, evidence_ids=[], source_ids=[], explanation="x")


def test_all_supported_is_draft_ready():
    state, _ = determine_response_state([_cv("C1", v.CLAIM_SUPPORTED), _cv("C2", v.CLAIM_SUPPORTED)])
    assert state == v.DRAFT_READY


def test_any_unsupported_blocks_the_whole_draft():
    state, reason = determine_response_state(
        [_cv("C1", v.CLAIM_SUPPORTED), _cv("C2", v.CLAIM_UNSUPPORTED)]
    )
    assert state == v.DRAFT_BLOCKED
    assert "C2" in reason


def test_any_invalid_reference_blocks_the_whole_draft():
    state, _ = determine_response_state([_cv("C1", v.CLAIM_INVALID_REFERENCE)])
    assert state == v.DRAFT_BLOCKED


def test_partially_supported_without_blocking_claims_flags_not_blocks():
    state, _ = determine_response_state([_cv("C1", v.CLAIM_SUPPORTED), _cv("C2", v.CLAIM_PARTIALLY_SUPPORTED)])
    assert state == v.DRAFT_FLAGGED


def test_blocked_takes_priority_over_flagged():
    state, _ = determine_response_state(
        [_cv("C1", v.CLAIM_PARTIALLY_SUPPORTED), _cv("C2", v.CLAIM_UNSUPPORTED)]
    )
    assert state == v.DRAFT_BLOCKED


def test_no_claims_at_all_is_blocked_not_ready():
    state, reason = determine_response_state([])
    assert state == v.DRAFT_BLOCKED
    assert reason


def test_single_unsupported_among_many_supported_still_blocks():
    """One bad claim blocks the whole response -- a merchant can't tell
    which parts of an otherwise-good draft to trust otherwise."""
    claims = [_cv(f"C{i}", v.CLAIM_SUPPORTED) for i in range(10)] + [_cv("C_bad", v.CLAIM_UNSUPPORTED)]
    state, reason = determine_response_state(claims)
    assert state == v.DRAFT_BLOCKED
    assert "C_bad" in reason
