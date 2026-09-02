"""Part G -- response safety policy.

Maps claim-level verification results to one of three response states.
Deliberately the simplest possible rule -- any single materially bad claim
blocks the whole response, because a merchant reading a "mostly grounded"
draft cannot tell which parts to trust unless the system already did that
work. Never automatically fixed/edited/removed -- a blocked draft is
surfaced to a human exactly as generated, with the reasons why.
"""

from __future__ import annotations

from app.evidence_intel import versions as v
from app.evidence_intel.verifier import ClaimVerification


def determine_response_state(verifications: list[ClaimVerification]) -> tuple[str, str]:
    """Returns (response_state, reason)."""
    if not verifications:
        return v.DRAFT_BLOCKED, "No claims were generated -- there is nothing to present as a grounded response."

    blocking = [
        c for c in verifications if c.status in (v.CLAIM_UNSUPPORTED, v.CLAIM_INVALID_REFERENCE, v.CLAIM_INCOMPLETE)
    ]
    if blocking:
        ids = ", ".join(c.claim_id for c in blocking)
        return (
            v.DRAFT_BLOCKED,
            f"Response contains {len(blocking)} unsupported, invalidly-referenced, or incomplete material "
            f"claim(s) ({ids}). Human review required before any of this draft can be used.",
        )

    flagged = [c for c in verifications if c.status == v.CLAIM_PARTIALLY_SUPPORTED]
    if flagged:
        ids = ", ".join(c.claim_id for c in flagged)
        return (
            v.DRAFT_FLAGGED,
            f"{len(flagged)} claim(s) ({ids}) are only partially supported (weak evidence) -- "
            "recommend human review before use.",
        )

    return v.DRAFT_READY, "All material claims are supported by this case's evidence and/or retrieved guidance."
