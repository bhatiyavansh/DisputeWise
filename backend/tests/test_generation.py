"""Part E -- structured generation output validation tests."""

import pytest

from app.evidence_intel import versions as v
from app.evidence_intel.generation import LLMOutputError, generate_draft
from app.evidence_intel.llm_provider import FakeLLMProvider
from app.evidence_intel.packet import build_packet
from app.evidence_intel.retrieval import retrieve_for_case


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
        _FakeEvidenceRow("delivery_confirmed", True, {"confirmed": True}, "high", 0.9, "EVD-001"),
        _FakeEvidenceRow("proof_of_delivery", False, None, "high", 0.0, "EVD-002"),
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


def _retrieval(packet):
    return retrieve_for_case(reason_code=packet.case.reason_code, gap=packet.gap, top_k=5)


VALID_PAYLOAD = {
    "summary": "Delivery confirmed; proof of delivery missing.",
    "claims": [
        {
            "claim_id": "C1",
            "text": "Delivery was confirmed for this transaction.",
            "claim_type": "fact",
            "evidence_ids": ["EVD-001"],
            "source_ids": [],
        }
    ],
    "missing_evidence": ["proof_of_delivery"],
    "response_body": "We contest this dispute based on confirmed delivery.",
}


def test_generate_draft_returns_validated_structure():
    packet = _packet()
    provider = FakeLLMProvider(response=VALID_PAYLOAD)
    draft = generate_draft(packet, _retrieval(packet), provider)

    assert draft.summary == VALID_PAYLOAD["summary"]
    assert len(draft.claims) == 1
    assert draft.claims[0].claim_id == "C1"
    assert draft.prompt_version == v.PROMPT_VERSION
    assert draft.response_schema_version == "response-v1"


def test_generate_draft_passes_prompt_context_to_provider():
    packet = _packet()
    provider = FakeLLMProvider(response=VALID_PAYLOAD)
    generate_draft(packet, _retrieval(packet), provider)

    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert "DSP-000001" in call["user"]
    assert "EVD-001" in call["user"]
    assert call["tool_name"] == "emit_grounded_draft"


def test_generate_draft_raises_on_missing_required_field():
    packet = _packet()
    bad_payload = dict(VALID_PAYLOAD)
    del bad_payload["response_body"]
    provider = FakeLLMProvider(response=bad_payload)
    with pytest.raises(LLMOutputError):
        generate_draft(packet, _retrieval(packet), provider)


def test_generate_draft_raises_on_wrong_type():
    packet = _packet()
    bad_payload = dict(VALID_PAYLOAD)
    bad_payload["claims"] = "not a list"
    provider = FakeLLMProvider(response=bad_payload)
    with pytest.raises(LLMOutputError):
        generate_draft(packet, _retrieval(packet), provider)


def test_generate_draft_raises_on_invalid_claim_type_enum():
    packet = _packet()
    bad_payload = dict(VALID_PAYLOAD)
    bad_payload["claims"] = [
        {"claim_id": "C1", "text": "x", "claim_type": "not_a_real_type", "evidence_ids": [], "source_ids": []}
    ]
    provider = FakeLLMProvider(response=bad_payload)
    with pytest.raises(LLMOutputError):
        generate_draft(packet, _retrieval(packet), provider)


def test_generate_draft_propagates_provider_failure():
    packet = _packet()
    provider = FakeLLMProvider(raise_error=True)
    with pytest.raises(LLMOutputError):
        generate_draft(packet, _retrieval(packet), provider)


def test_generate_draft_deterministic_given_same_provider_response():
    packet = _packet()
    provider = FakeLLMProvider(response=VALID_PAYLOAD)
    first = generate_draft(packet, _retrieval(packet), provider)
    second = generate_draft(packet, _retrieval(packet), provider)
    assert first == second
