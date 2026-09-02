"""Regression tests for the verifier-v1.1 / prompt-v1.1 hardening pass.

Triggered by the first live OpenRouter run on DSP-031597, which surfaced two
real defects that the pre-existing test suite did not catch:

  1. A claim (C16) cited the evidence_id of MISSING proof_of_delivery while
     stating (correctly, in prose) that it was absent -- the verifier still
     (correctly) rejected it as "cites unavailable evidence", but the root
     cause was the prompt itself: its "Available Evidence IDs" list included
     unavailable evidence_ids, so the model had actually been told it could
     cite them.
  2. The generated response_body ended mid-sentence: "Proof of delivery is: "
     -- nothing in the pipeline detected or blocked a truncated response.

  Additionally, C15 argued that other evidence "supports that the goods
  were delivered" *despite* proof_of_delivery being absent -- a rhetorical
  overreach that isn't caught by any citation-based check, since it cited
  no missing evidence_id at all.

Scenarios A-D below are the four the hardening request explicitly asked for.
E (13/13 adversarial), F (OpenRouter provider tests), and G (full Phase 1-3
regression) are the existing suites, confirmed green by the full `pytest -q`
run alongside this file, not duplicated here. H (locked dataset) is verified
by shell commands, not a pytest test -- see the final report.
"""

from __future__ import annotations

import pytest

from app.evidence_intel import versions as v
from app.evidence_intel.generation import GeneratedClaim, generate_draft
from app.evidence_intel.llm_provider import FakeLLMProvider
from app.evidence_intel.packet import build_packet
from app.evidence_intel.retrieval import retrieve_for_case
from app.evidence_intel.safety import determine_response_state
from app.evidence_intel.verifier import verify_claim, verify_claims, verify_response_body


class _FakeEvidenceRow:
    def __init__(self, evidence_type, available, value, relevance, strength, evidence_id):
        self.evidence_type = evidence_type
        self.available = available
        self.value = value
        self.relevance = relevance
        self.strength = strength
        self.evidence_id = evidence_id


def _dsp_031597_like_packet():
    """Mirrors the real DSP-031597 shape closely enough to reproduce the live
    failure: several strong, available, high-relevance goods_not_received
    evidence items, with proof_of_delivery specifically missing."""
    rows = [
        _FakeEvidenceRow("delivery_confirmed", True, {"confirmed": True}, "high", 0.9, "EVD-CONFIRMED"),
        _FakeEvidenceRow("delivery_address_match", True, {"match": True}, "high", 0.85, "EVD-ADDRMATCH"),
        _FakeEvidenceRow("delivery_timestamp", True, {"timestamp": "2026-10-13T11:07:00Z"}, "high", 0.8, "EVD-TIMESTAMP"),
        _FakeEvidenceRow("tracking_available", True, {"available": True}, "high", 0.75, "EVD-TRACKING"),
        _FakeEvidenceRow("proof_of_delivery", False, None, "high", 0.0, "EVD-POD"),  # the missing critical item
        _FakeEvidenceRow("customer_communication_available", True, {"present": True}, "medium", 0.7, "EVD-COMMS"),
    ]
    return build_packet(
        dispute_id="DSP-031597",
        reason_code="goods_not_received",
        dispute_amount=27531.38,
        dispute_status="open",
        created_at="2026-01-01T00:00:00+00:00",
        payment_method="upi",
        transaction_status="captured",
        three_ds_authenticated=True,
        avs_result="Y",
        cvv_result="M",
        account_age_days=135,
        previous_order_count=5,
        previous_successful_order_count=4,
        previous_dispute_count=0,
        previous_refund_count=0,
        evidence_rows=rows,
    )


def _retrieval(packet):
    return retrieve_for_case(reason_code=packet.case.reason_code, gap=packet.gap, top_k=6)


# ---------------------------------------------------------------------------
# A. Missing evidence cited as evidence -> BLOCKED
# ---------------------------------------------------------------------------


def test_a_claim_citing_missing_evidence_id_is_unsupported():
    """Reproduces C16's exact shape: a claim that correctly states proof of
    delivery is absent, but does so by citing EVD-POD's evidence_id anyway."""
    packet = _dsp_031597_like_packet()
    claim = GeneratedClaim(
        claim_id="C16",
        text="Proof of delivery is not on file for this transaction.",
        claim_type="fact",
        evidence_ids=["EVD-POD"],  # the bug: citing the ID of evidence that is unavailable
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_UNSUPPORTED
    assert "unavailable" in result.explanation.lower()


def test_a_end_to_end_missing_evidence_citation_blocks_the_whole_draft():
    packet = _dsp_031597_like_packet()
    retrieval = _retrieval(packet)
    payload = {
        "summary": "s",
        "claims": [
            {
                "claim_id": "C1",
                "text": "Delivery was confirmed for this transaction.",
                "claim_type": "fact",
                "evidence_ids": ["EVD-CONFIRMED"],
                "source_ids": [],
            },
            {
                "claim_id": "C16",
                "text": "Proof of delivery is not on file for this transaction.",
                "claim_type": "fact",
                "evidence_ids": ["EVD-POD"],
                "source_ids": [],
            },
        ],
        "missing_evidence": ["proof_of_delivery"],
        "response_body": "We contest this dispute citing confirmed delivery.",
    }
    draft = generate_draft(packet, retrieval, FakeLLMProvider(response=payload))
    verifications = verify_claims(draft.claims, packet, retrieval)
    verifications = verifications + [verify_response_body(draft.response_body)]
    response_state, reason = determine_response_state(verifications)

    assert response_state == v.DRAFT_BLOCKED
    assert "C16" in reason


# ---------------------------------------------------------------------------
# B. Generated response ending with ":" -> BLOCKED
# ---------------------------------------------------------------------------


def test_b_response_body_ending_in_colon_is_incomplete():
    result = verify_response_body("Proof of delivery is: ")
    assert result.status == v.CLAIM_INCOMPLETE
    assert result.claim_id == "RESPONSE_BODY"


def test_b_response_body_ending_in_colon_blocks_the_whole_draft_even_if_all_claims_are_fine():
    """The exact live failure mode: every individual claim was fine; the
    dangling text was only in response_body. Must still block."""
    packet = _dsp_031597_like_packet()
    retrieval = _retrieval(packet)
    payload = {
        "summary": "s",
        "claims": [
            {
                "claim_id": "C1",
                "text": "Delivery was confirmed for this transaction.",
                "claim_type": "fact",
                "evidence_ids": ["EVD-CONFIRMED"],
                "source_ids": [],
            }
        ],
        "missing_evidence": ["proof_of_delivery"],
        "response_body": "We contest this dispute citing confirmed delivery. Proof of delivery is: ",
    }
    draft = generate_draft(packet, retrieval, FakeLLMProvider(response=payload))
    verifications = verify_claims(draft.claims, packet, retrieval)
    verifications = verifications + [verify_response_body(draft.response_body)]
    response_state, reason = determine_response_state(verifications)

    assert verifications[0].status == v.CLAIM_SUPPORTED  # the one real claim is fine
    assert response_state == v.DRAFT_BLOCKED  # but the response_body itself is dangling
    assert "RESPONSE_BODY" in reason


@pytest.mark.parametrize(
    "text",
    [
        "Proof of delivery is: ",
        "The evidence shows;",
        "This claim is supported by,",
        "Delivery confirmation and tracking evidence -",
        "The following evidence supports this claim: (",
        "",
        "   ",
    ],
)
def test_b_various_dangling_endings_are_incomplete(text):
    assert verify_response_body(text).status == v.CLAIM_INCOMPLETE


@pytest.mark.parametrize(
    "text",
    [
        "Delivery was confirmed for this transaction.",
        "Is proof of delivery on file?",
        "This is remarkable!",
        'The evidence states "delivery was confirmed."',
        "The record (verified) is complete.",
    ],
)
def test_b_properly_terminated_text_is_complete(text):
    assert verify_response_body(text).status == v.CLAIM_SUPPORTED


# ---------------------------------------------------------------------------
# C. Missing proof_of_delivery + otherwise strong evidence -> the model
#    cannot produce an accepted assertion that proof_of_delivery exists,
#    whether via direct citation (already A) or rhetorical overreach.
# ---------------------------------------------------------------------------


def test_c_inference_overreach_around_missing_proof_of_delivery_is_rejected():
    """Reproduces C15's exact live wording."""
    packet = _dsp_031597_like_packet()
    claim = GeneratedClaim(
        claim_id="C15",
        text=(
            "Despite the absence of proof of delivery, the combination of delivery confirmation, "
            "address match, timestamp, and tracking supports that the goods were delivered to the "
            "cardholder."
        ),
        claim_type="inference",
        evidence_ids=["EVD-CONFIRMED", "EVD-ADDRMATCH", "EVD-TIMESTAMP", "EVD-TRACKING"],
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_UNSUPPORTED
    assert "overcomes the absence" in result.explanation.lower() or "overreach" in result.explanation.lower() or "rhetorically" in result.explanation.lower()


@pytest.mark.parametrize(
    "text",
    [
        "Even without proof of delivery, tracking and address match confirm the goods arrived.",
        "Notwithstanding the missing proof of delivery, delivery confirmation demonstrates fulfillment.",
        "In spite of the lack of proof of delivery, the available evidence establishes delivery occurred.",
    ],
)
def test_c_inference_overreach_phrasing_variants_are_rejected(text):
    packet = _dsp_031597_like_packet()
    claim = GeneratedClaim(
        claim_id="C1", text=text, claim_type="inference",
        evidence_ids=["EVD-CONFIRMED", "EVD-TRACKING"], source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_UNSUPPORTED


def test_c_overreach_check_only_applies_to_inference_claims():
    """A 'fact' claim using similar absence language is still checked by the
    OTHER rules (citation/availability), but not rejected BY THE OVERREACH
    RULE specifically -- it's rejected because it doesn't cite the missing
    item at all, so it's just an ordinary supported claim about fact."""
    packet = _dsp_031597_like_packet()
    claim = GeneratedClaim(
        claim_id="C1",
        text="Despite the absence of proof of delivery, delivery confirmation shows the order was fulfilled.",
        claim_type="fact",  # not "inference" -- overreach guard is inference-only by design
        evidence_ids=["EVD-CONFIRMED"],
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    # Not rejected by the overreach guard (fact claims aren't checked by it);
    # whether it ends up SUPPORTED is incidental to this test's point.
    assert "overcomes the absence" not in result.explanation.lower()


def test_c_cannot_construct_an_end_to_end_draft_asserting_pod_exists():
    """No path through generate_draft + verify_claims + determine_response_state
    accepts a claim asserting proof_of_delivery exists for this case --
    whether by direct citation (A) or inference overreach (C15's pattern)."""
    packet = _dsp_031597_like_packet()
    retrieval = _retrieval(packet)
    payload = {
        "summary": "s",
        "claims": [
            {
                "claim_id": "C15",
                "text": (
                    "Despite the absence of proof of delivery, the combination of delivery "
                    "confirmation and tracking supports that the goods were delivered."
                ),
                "claim_type": "inference",
                "evidence_ids": ["EVD-CONFIRMED", "EVD-TRACKING"],
                "source_ids": [],
            }
        ],
        "missing_evidence": ["proof_of_delivery"],
        "response_body": "We contest this dispute based on delivery confirmation.",
    }
    draft = generate_draft(packet, retrieval, FakeLLMProvider(response=payload))
    verifications = verify_claims(draft.claims, packet, retrieval)
    verifications = verifications + [verify_response_body(draft.response_body)]
    response_state, _ = determine_response_state(verifications)
    assert response_state == v.DRAFT_BLOCKED


# ---------------------------------------------------------------------------
# D. Safe, cautious statement about missing evidence -> allowed
# ---------------------------------------------------------------------------


def test_d_pure_missing_evidence_statement_with_no_citations_is_supported():
    """Reproduces the LIVE OpenRouter response's C5 claim exactly, after the
    first hardening pass: the model correctly followed the new prompt rule
    (state absence with EMPTY evidence_ids instead of citing the missing
    item's ID), which the verifier's plain "cites nothing -> UNSUPPORTED"
    rule then incorrectly rejected -- there is no ID to cite for something
    that doesn't exist. This is the fix for that second-order finding."""
    packet = _dsp_031597_like_packet()
    claim = GeneratedClaim(
        claim_id="C5",
        text="Proof of delivery (such as a signed receipt) is not available in the case file.",
        claim_type="fact",
        evidence_ids=[],
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_SUPPORTED


def test_d_pure_missing_evidence_statement_still_requires_no_conclusion():
    """Guard: a zero-citation claim that mentions a missing item BUT also
    draws a conclusion ("supports"/"confirms"/...) must still be rejected --
    the carve-out is for reporting absence, not laundering an unsupported
    conclusion through it."""
    packet = _dsp_031597_like_packet()
    claim = GeneratedClaim(
        claim_id="C1",
        text="Proof of delivery is missing, but this confirms the customer's claim is valid.",
        claim_type="fact",
        evidence_ids=[],
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_UNSUPPORTED


def test_d_zero_citation_claim_unrelated_to_any_gap_still_unsupported():
    """Guard: the carve-out must not become a general 'zero citations are
    fine' loophole -- a claim mentioning no missing evidence type at all is
    still rejected exactly as before."""
    packet = _dsp_031597_like_packet()
    claim = GeneratedClaim(
        claim_id="C1",
        text="The customer has a long history of legitimate purchases.",
        claim_type="inference",
        evidence_ids=[],
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_UNSUPPORTED
    assert "cites no evidence" in result.explanation.lower()


def test_d_end_to_end_live_reproduction_is_draft_blocked_only_by_the_real_issue():
    """Reproduces the full live draft shape (6 claims mirroring what
    OpenRouter actually returned) to confirm C1-C4 and C6 are SUPPORTED, C5
    (a pure missing-evidence statement) is now also SUPPORTED after this
    fix, and the response_body (which was complete in the live run) doesn't
    block either -- i.e. the corrected pipeline would now have produced
    DRAFT_READY for this exact draft, not DRAFT_BLOCKED."""
    packet = _dsp_031597_like_packet()
    retrieval = _retrieval(packet)
    payload = {
        "summary": "s",
        "claims": [
            {
                "claim_id": "C1",
                "text": "Delivery was confirmed, with a matching address and a recorded delivery timestamp.",
                "claim_type": "fact",
                "evidence_ids": ["EVD-CONFIRMED", "EVD-ADDRMATCH", "EVD-TIMESTAMP"],
                "source_ids": [],
            },
            {
                "claim_id": "C2",
                "text": "Tracking information is available for this transaction.",
                "claim_type": "fact",
                "evidence_ids": ["EVD-TRACKING"],
                "source_ids": [],
            },
            {
                "claim_id": "C3",
                "text": "Customer communication records are available for this order.",
                "claim_type": "fact",
                "evidence_ids": ["EVD-COMMS"],
                "source_ids": [],
            },
            {
                "claim_id": "C4",
                "text": "Per Stripe's guidance, proof of delivery is highly relevant evidence for goods-not-received disputes.",
                "claim_type": "reference",
                "evidence_ids": [],
                "source_ids": ["stripe_dispute_reason_codes_2026"],
            },
            {
                "claim_id": "C5",
                "text": "Proof of delivery is not available in the case file.",
                "claim_type": "fact",
                "evidence_ids": [],
                "source_ids": [],
            },
            {
                "claim_id": "C6",
                "text": "The available evidence shows delivery was confirmed and tracked, but proof of delivery is currently missing.",
                "claim_type": "summary",
                "evidence_ids": ["EVD-CONFIRMED", "EVD-TRACKING"],
                "source_ids": [],
            },
        ],
        "missing_evidence": ["proof_of_delivery"],
        "response_body": (
            "This dispute is contested based on confirmed delivery, a matching address, tracking, and "
            "customer communication records. Proof of delivery is currently missing from our records."
        ),
    }
    draft = generate_draft(packet, retrieval, FakeLLMProvider(response=payload))
    verifications = verify_claims(draft.claims, packet, retrieval)
    verifications = verifications + [verify_response_body(draft.response_body)]
    response_state, reason = determine_response_state(verifications)

    statuses = {c.claim_id: c.status for c in verifications}
    assert statuses == {
        "C1": v.CLAIM_SUPPORTED,
        "C2": v.CLAIM_SUPPORTED,
        "C3": v.CLAIM_SUPPORTED,
        "C4": v.CLAIM_SUPPORTED,
        "C5": v.CLAIM_SUPPORTED,
        "C6": v.CLAIM_SUPPORTED,
        "RESPONSE_BODY": v.CLAIM_SUPPORTED,
    }
    assert response_state == v.DRAFT_READY


def test_d_cautious_missing_evidence_statement_is_supported():
    """The exact pattern the hardened prompt now asks for: state what IS
    available, then separately and plainly note what's missing -- no
    citation of the missing item, no rhetorical override."""
    packet = _dsp_031597_like_packet()
    claim = GeneratedClaim(
        claim_id="C1",
        text=(
            "The available evidence includes delivery confirmation, address match, and tracking, "
            "but proof of delivery is currently missing."
        ),
        claim_type="fact",
        evidence_ids=["EVD-CONFIRMED", "EVD-ADDRMATCH", "EVD-TRACKING"],
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_SUPPORTED


def test_d_cautious_statement_as_inference_type_is_also_supported():
    """Same cautious pattern, but claim_type=inference -- proves the overreach
    guard doesn't over-trigger on safe inference wording that mentions a
    missing item without absence-cue + support-conclusion language together."""
    packet = _dsp_031597_like_packet()
    claim = GeneratedClaim(
        claim_id="C2",
        text=(
            "Based on delivery confirmation and tracking, fulfillment appears likely, though proof of "
            "delivery is currently missing and was not considered here."
        ),
        claim_type="inference",
        evidence_ids=["EVD-CONFIRMED", "EVD-TRACKING"],
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_SUPPORTED


def test_d_end_to_end_cautious_draft_is_draft_ready():
    packet = _dsp_031597_like_packet()
    retrieval = _retrieval(packet)
    payload = {
        "summary": "Strong delivery evidence; proof of delivery is the one gap.",
        "claims": [
            {
                "claim_id": "C1",
                "text": "Delivery was confirmed, with a matching address and available tracking.",
                "claim_type": "fact",
                "evidence_ids": ["EVD-CONFIRMED", "EVD-ADDRMATCH", "EVD-TRACKING"],
                "source_ids": [],
            },
            {
                "claim_id": "C2",
                "text": (
                    "The available evidence includes delivery confirmation, address match, and tracking, "
                    "but proof of delivery is currently missing."
                ),
                "claim_type": "fact",
                "evidence_ids": ["EVD-CONFIRMED", "EVD-ADDRMATCH", "EVD-TRACKING"],
                "source_ids": [],
            },
        ],
        "missing_evidence": ["proof_of_delivery"],
        "response_body": (
            "This dispute is contested on the basis of confirmed delivery, a matching delivery "
            "address, and available tracking information. Proof of delivery is currently missing "
            "from our records."
        ),
    }
    draft = generate_draft(packet, retrieval, FakeLLMProvider(response=payload))
    verifications = verify_claims(draft.claims, packet, retrieval)
    verifications = verifications + [verify_response_body(draft.response_body)]
    response_state, reason = determine_response_state(verifications)

    assert all(c.status == v.CLAIM_SUPPORTED for c in verifications)
    assert response_state == v.DRAFT_READY
