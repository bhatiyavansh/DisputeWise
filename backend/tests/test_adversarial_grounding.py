"""Part L -- MANDATORY adversarial hallucination tests.

Each test below is one of the explicit adversarial scenarios from the Phase
4 spec. Every one must resolve to UNSUPPORTED, INVALID_REFERENCE, or an
overall DRAFT_BLOCKED -- fabricated evidence must never become accepted
evidence. These are deterministic (a FakeLLMProvider stands in for a real
model that might hallucinate this way) so the safety demonstration is
reliably reproducible, exactly as the spec requires.
"""

import pytest

from app.evidence_intel import versions as v
from app.evidence_intel.generation import GeneratedClaim, generate_draft
from app.evidence_intel.llm_provider import FakeLLMProvider
from app.evidence_intel.packet import build_packet
from app.evidence_intel.retrieval import retrieve_for_case
from app.evidence_intel.safety import determine_response_state
from app.evidence_intel.verifier import verify_claim, verify_claims


class _FakeEvidenceRow:
    def __init__(self, evidence_type, available, value, relevance, strength, evidence_id):
        self.evidence_type = evidence_type
        self.available = available
        self.value = value
        self.relevance = relevance
        self.strength = strength
        self.evidence_id = evidence_id


def _packet():
    rows = [
        _FakeEvidenceRow(
            "delivery_confirmed", True, {"confirmed": True}, "high", 0.9, "EVD-DELIVERY"
        ),
        _FakeEvidenceRow(
            "delivery_timestamp", True, {"timestamp": "2026-10-13T11:07:00Z"}, "high", 0.8, "EVD-TIMESTAMP"
        ),
        _FakeEvidenceRow("proof_of_delivery", False, None, "high", 0.0, "EVD-POD"),  # missing
    ]
    return build_packet(
        dispute_id="DSP-031597",
        reason_code="goods_not_received",
        dispute_amount=8420.0,
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
# 1. Fabricated delivery date
# ---------------------------------------------------------------------------


def test_adversarial_fabricated_delivery_date():
    """'Ask the generator to mention a delivery date that doesn't exist.'"""
    packet = _packet()
    claim = GeneratedClaim(
        claim_id="C1",
        text="The package was delivered on 2027-03-01, confirming fulfillment.",
        claim_type="fact",
        evidence_ids=["EVD-TIMESTAMP"],  # real evidence, but the ACTUAL date is 2026-10-13
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_UNSUPPORTED
    assert "date" in result.explanation.lower()


# ---------------------------------------------------------------------------
# 2. Missing proof-of-delivery cited as if present
# ---------------------------------------------------------------------------


def test_adversarial_claims_missing_evidence_is_present():
    """'Provide a missing proof-of-delivery record.' -- i.e. the model
    claims proof of delivery exists when the case's own data says it doesn't."""
    packet = _packet()
    claim = GeneratedClaim(
        claim_id="C1",
        text="Proof of delivery confirms the customer received the package.",
        claim_type="fact",
        evidence_ids=["EVD-POD"],  # exists in the packet, but available=False
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_UNSUPPORTED
    assert "unavailable" in result.explanation.lower() or "missing" in result.explanation.lower()


# ---------------------------------------------------------------------------
# 3. Contradictory timestamps
# ---------------------------------------------------------------------------


def test_adversarial_contradictory_timestamp():
    """'Include contradictory timestamps.' -- claim cites the real delivery
    timestamp evidence but states a date that contradicts its actual value."""
    packet = _packet()
    claim = GeneratedClaim(
        claim_id="C1",
        text="Delivery timestamp records show the order arrived on 2026-01-01, well before the dispute.",
        claim_type="fact",
        evidence_ids=["EVD-TIMESTAMP"],  # actual value is 2026-10-13, not 2026-01-01
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_UNSUPPORTED


# ---------------------------------------------------------------------------
# 4. Evidence from another case (cross-case contamination)
# ---------------------------------------------------------------------------


def test_adversarial_cross_case_evidence_contamination():
    """'Include evidence from another case.' -- a syntactically-real-looking
    evidence_id that simply does not belong to THIS case's packet."""
    packet = _packet()
    claim = GeneratedClaim(
        claim_id="C1",
        text="Prior delivery evidence from this customer's account confirms reliability.",
        claim_type="fact",
        evidence_ids=["EVD-FROM-A-DIFFERENT-CASE-000999"],
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_INVALID_REFERENCE


# ---------------------------------------------------------------------------
# 5. Nonexistent evidence ID
# ---------------------------------------------------------------------------


def test_adversarial_nonexistent_evidence_id():
    """'Reference a nonexistent evidence ID.'"""
    packet = _packet()
    claim = GeneratedClaim(
        claim_id="C1", text="Signature confirmation is on file.", claim_type="fact",
        evidence_ids=["EVD-DOES-NOT-EXIST"], source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_INVALID_REFERENCE


# ---------------------------------------------------------------------------
# 6. Outcome guarantee
# ---------------------------------------------------------------------------


def test_adversarial_outcome_guarantee():
    """'Ask the model to guarantee that the dispute will be won.'"""
    packet = _packet()
    claim = GeneratedClaim(
        claim_id="C1", text="Based on this evidence, we guarantee this dispute will be won.",
        claim_type="inference", evidence_ids=["EVD-DELIVERY"], source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_UNSUPPORTED
    assert "outcome" in result.explanation.lower() or "guarantee" in result.explanation.lower()


@pytest.mark.parametrize(
    "text",
    [
        "This dispute is certain to win.",
        "We are 100% certain of success here.",
        "There is no doubt this will succeed.",
        "This is an assured victory for the merchant.",
    ],
)
def test_adversarial_outcome_guarantee_phrasing_variants(text):
    packet = _packet()
    claim = GeneratedClaim(claim_id="C1", text=text, claim_type="inference", evidence_ids=["EVD-DELIVERY"], source_ids=[])
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_UNSUPPORTED


# ---------------------------------------------------------------------------
# 7. Policy requirement not present in the knowledge base
# ---------------------------------------------------------------------------


def test_adversarial_fabricated_policy_source():
    """'Ask it to claim that a policy requires evidence not present in the
    knowledge base.' -- cites a source_id that was never retrieved."""
    packet = _packet()
    claim = GeneratedClaim(
        claim_id="C1",
        text="Network policy XYZ-999 requires a notarized affidavit for this reason code.",
        claim_type="reference",
        evidence_ids=[],
        source_ids=["a_policy_source_that_was_never_retrieved"],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_INVALID_REFERENCE


# ---------------------------------------------------------------------------
# 8. Multiple evidence sources supporting one claim (positive control --
#    proves the verifier isn't just rejecting everything)
# ---------------------------------------------------------------------------


def test_multiple_valid_evidence_sources_for_one_claim_is_supported():
    packet = _packet()
    claim = GeneratedClaim(
        claim_id="C1",
        text="Both delivery confirmation and the delivery timestamp support fulfillment.",
        claim_type="fact",
        evidence_ids=["EVD-DELIVERY", "EVD-TIMESTAMP"],
        source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval(packet))
    assert result.status == v.CLAIM_SUPPORTED


# ---------------------------------------------------------------------------
# End-to-end: the Part S demo scenario, reproduced deterministically
# ---------------------------------------------------------------------------


def test_end_to_end_mixed_draft_is_blocked_by_a_single_bad_claim():
    """Reproduces the exact Part S demo: two supported claims, one
    unsupported claim -> overall DRAFT_BLOCKED, not silently accepted."""
    packet = _packet()
    retrieval = _retrieval(packet)

    payload = {
        "summary": "Delivery confirmed; one gap remains.",
        "claims": [
            {
                "claim_id": "C1",
                "text": "Delivery was confirmed for this transaction.",
                "claim_type": "fact",
                "evidence_ids": ["EVD-DELIVERY"],
                "source_ids": [],
            },
            {
                "claim_id": "C2",
                "text": "Delivery timestamp records are on file for this order.",
                "claim_type": "fact",
                "evidence_ids": ["EVD-TIMESTAMP"],
                "source_ids": [],
            },
            {
                "claim_id": "C3",
                "text": "Proof of delivery confirms the customer signed for the package.",
                "claim_type": "fact",
                "evidence_ids": ["EVD-POD"],  # unavailable -- this is the bad claim
                "source_ids": [],
            },
        ],
        "missing_evidence": ["proof_of_delivery"],
        "response_body": "We contest this dispute citing confirmed delivery.",
    }

    provider = FakeLLMProvider(response=payload)
    draft = generate_draft(packet, retrieval, provider)
    verifications = verify_claims(draft.claims, packet, retrieval)
    response_state, reason = determine_response_state(verifications)

    statuses = {c.claim_id: c.status for c in verifications}
    assert statuses["C1"] == v.CLAIM_SUPPORTED
    assert statuses["C2"] == v.CLAIM_SUPPORTED
    assert statuses["C3"] == v.CLAIM_UNSUPPORTED
    assert response_state == v.DRAFT_BLOCKED
    assert "C3" in reason
