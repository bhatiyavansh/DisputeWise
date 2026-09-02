"""Part F -- claim-level grounding verifier: core logic tests.

Adversarial/hallucination-focused scenarios (Part L) live in
test_adversarial_grounding.py; this file covers the verifier's ordinary
SUPPORTED / PARTIALLY_SUPPORTED behavior and the building blocks each
adversarial check relies on.
"""

from app.evidence_intel import versions as v
from app.evidence_intel.generation import GeneratedClaim
from app.evidence_intel.packet import build_packet
from app.evidence_intel.retrieval import RetrievalResult
from app.evidence_intel.verifier import verify_claim, verify_claims


class _FakeEvidenceRow:
    def __init__(self, evidence_type, available, value, relevance, strength, evidence_id):
        self.evidence_type = evidence_type
        self.available = available
        self.value = value
        self.relevance = relevance
        self.strength = strength
        self.evidence_id = evidence_id


def _packet(rows=None):
    rows = rows or [
        _FakeEvidenceRow(
            "delivery_confirmed", True, {"confirmed": True, "timestamp": "2026-10-13T11:07:00Z"}, "high", 0.9, "EVD-001"
        ),
        _FakeEvidenceRow("proof_of_delivery", False, None, "high", 0.0, "EVD-002"),
        _FakeEvidenceRow("tracking_available", True, {"available": True}, "high", 0.15, "EVD-003"),  # weak
    ]
    return build_packet(
        dispute_id="DSP-000001",
        reason_code="goods_not_received",
        dispute_amount=1999.0,
        dispute_status="open",
        created_at="2026-01-01T00:00:00+00:00",
        payment_method="card",
        transaction_status="captured",
        three_ds_authenticated=True,
        avs_result="Y",
        cvv_result="M",
        account_age_days=400,
        previous_order_count=12,
        previous_successful_order_count=11,
        previous_dispute_count=0,
        previous_refund_count=1,
        evidence_rows=rows,
    )


def _retrieval():
    return [
        RetrievalResult(
            chunk_id="evidence:goods_not_received:proof_of_delivery",
            text="guidance text",
            source_id="stripe_dispute_reason_codes_2026",
            source_name="Stripe",
            source_url="https://docs.stripe.com/disputes/reason-codes-defense-requirements",
            relevance_score=0.9,
            metadata={},
        )
    ]


def test_claim_grounded_in_available_evidence_is_supported():
    packet = _packet()
    claim = GeneratedClaim(claim_id="C1", text="Delivery was confirmed.", claim_type="fact", evidence_ids=["EVD-001"], source_ids=[])
    result = verify_claim(claim, packet, _retrieval())
    assert result.status == v.CLAIM_SUPPORTED


def test_claim_grounded_in_source_is_supported():
    packet = _packet()
    claim = GeneratedClaim(
        claim_id="C1",
        text="Per network guidance, delivery evidence matters here.",
        claim_type="reference",
        evidence_ids=[],
        source_ids=["stripe_dispute_reason_codes_2026"],
    )
    result = verify_claim(claim, packet, _retrieval())
    assert result.status == v.CLAIM_SUPPORTED


def test_claim_citing_weak_evidence_is_partially_supported():
    packet = _packet()
    claim = GeneratedClaim(claim_id="C1", text="Tracking is available.", claim_type="fact", evidence_ids=["EVD-003"], source_ids=[])
    result = verify_claim(claim, packet, _retrieval())
    assert result.status == v.CLAIM_PARTIALLY_SUPPORTED
    assert "weak" in result.explanation.lower()


def test_claim_mixing_strong_and_weak_evidence_is_partially_supported():
    packet = _packet()
    claim = GeneratedClaim(
        claim_id="C1", text="Delivery and tracking both support this.", claim_type="fact",
        evidence_ids=["EVD-001", "EVD-003"], source_ids=[],
    )
    result = verify_claim(claim, packet, _retrieval())
    assert result.status == v.CLAIM_PARTIALLY_SUPPORTED


def test_verify_claims_processes_a_list_independently():
    packet = _packet()
    claims = [
        GeneratedClaim(claim_id="C1", text="Delivery was confirmed.", claim_type="fact", evidence_ids=["EVD-001"], source_ids=[]),
        GeneratedClaim(claim_id="C2", text="Proof of delivery confirms the timeline.", claim_type="fact", evidence_ids=["EVD-002"], source_ids=[]),
    ]
    results = verify_claims(claims, packet, _retrieval())
    assert results[0].status == v.CLAIM_SUPPORTED
    assert results[1].status == v.CLAIM_UNSUPPORTED  # EVD-002 exists but is unavailable
    assert [r.claim_id for r in results] == ["C1", "C2"]


def test_explanation_is_never_empty():
    packet = _packet()
    claim = GeneratedClaim(claim_id="C1", text="Anything.", claim_type="fact", evidence_ids=["EVD-001"], source_ids=[])
    result = verify_claim(claim, packet, _retrieval())
    assert result.explanation.strip()


def test_verifier_version_stamped_on_result():
    packet = _packet()
    claim = GeneratedClaim(claim_id="C1", text="x", claim_type="fact", evidence_ids=["EVD-001"], source_ids=[])
    result = verify_claim(claim, packet, _retrieval())
    assert result.verifier_version == v.VERIFIER_VERSION


def test_verification_deterministic():
    packet = _packet()
    claim = GeneratedClaim(claim_id="C1", text="Delivery was confirmed.", claim_type="fact", evidence_ids=["EVD-001"], source_ids=[])
    first = verify_claim(claim, packet, _retrieval())
    second = verify_claim(claim, packet, _retrieval())
    assert first == second
