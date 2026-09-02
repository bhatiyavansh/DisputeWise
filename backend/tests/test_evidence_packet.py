"""Part B -- Evidence Packet tests."""

from app.evidence_intel.packet import build_packet
from app.evidence_intel.reference_data import load_reference_data


class _FakeEvidenceRow:
    def __init__(self, evidence_type, available, value, relevance, strength, evidence_id):
        self.evidence_type = evidence_type
        self.available = available
        self.value = value
        self.relevance = relevance
        self.strength = strength
        self.evidence_id = evidence_id


def _make_rows():
    return [
        _FakeEvidenceRow("delivery_confirmed", True, {"confirmed": True}, "high", 0.9, "EVD-001"),
        _FakeEvidenceRow("proof_of_delivery", False, None, "high", 0.0, "EVD-002"),
        _FakeEvidenceRow("tracking_available", True, {"available": True}, "high", 0.7, "EVD-003"),
    ]


def _build(**overrides):
    defaults = dict(
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
        evidence_rows=_make_rows(),
    )
    defaults.update(overrides)
    return build_packet(**defaults)


def test_packet_contains_case_transaction_customer_facts():
    packet = _build()
    assert packet.case.dispute_id == "DSP-000001"
    assert packet.case.reason_code == "goods_not_received"
    assert packet.transaction.payment_method == "card"
    assert packet.customer.previous_order_count == 12


def test_packet_evidence_items_have_stable_unique_ids():
    packet = _build()
    ids = [item.evidence_id for item in packet.evidence]
    assert len(ids) == len(set(ids))  # unique
    assert "EVD-001" in ids


def test_packet_evidence_marked_available_matches_source_row():
    packet = _build()
    by_type = {item.evidence_type: item for item in packet.evidence}
    assert by_type["delivery_confirmed"].available is True
    assert by_type["proof_of_delivery"].available is False


def test_packet_evidence_claim_type_is_fact():
    """Every case evidence item is FACT (on file for this case) per the
    FACT/REFERENCE/INFERENCE distinction in docs/phase4.md."""
    packet = _build()
    assert all(item.claim_type == "fact" for item in packet.evidence)


def test_packet_guidance_is_reference_type():
    packet = _build()
    assert packet.guidance.claim_type == "reference"
    assert packet.guidance.reason_code_id == "goods_not_received"
    assert packet.guidance.source_id


def test_packet_embeds_gap_analysis():
    packet = _build()
    assert packet.gap.reason_code == "goods_not_received"
    assert packet.gap.missing_count >= 1  # proof_of_delivery is missing


def test_packet_excludes_raw_pii_fields():
    """No device_id, ip_address, billing/shipping address, or country
    anywhere in the packet -- see packet.py's module docstring."""
    packet_dict = _build().to_dict()
    serialized = str(packet_dict)
    for forbidden in ("device_id", "ip_address", "billing_address", "shipping_address", "country"):
        assert forbidden not in serialized, f"packet leaked a raw/sensitive field: {forbidden}"


def test_packet_excludes_outcome_fields():
    """No favorable_outcome / recovery_amount / outcome_at reachable --
    mirrors the structural leakage guard in app/ml/features.py."""
    packet_dict = _build().to_dict()
    serialized = str(packet_dict)
    for forbidden in ("favorable_outcome", "recovery_amount", "outcome_at", "outcome_source"):
        assert forbidden not in serialized


def test_packet_evidence_by_id_lookup():
    packet = _build()
    lookup = packet.evidence_by_id()
    assert lookup["EVD-001"].evidence_type == "delivery_confirmed"
    assert "EVD-999" not in lookup


def test_packet_is_serializable_to_dict():
    packet = _build()
    payload = packet.to_dict()
    assert payload["case"]["dispute_id"] == "DSP-000001"
    assert isinstance(payload["evidence"], list)
    assert isinstance(payload["gap"]["items"], list)


def test_packet_unknown_reason_code_raises():
    import pytest

    with pytest.raises(ValueError, match="no reference evidence requirements"):
        _build(reason_code="not_a_real_reason_code")


def test_packet_reference_data_injectable_for_testing():
    """Confirms the packet builder accepts an explicit ReferenceData (used
    throughout this test file implicitly via the default cached loader, and
    explicitly here) rather than only working against the real files."""
    reference = load_reference_data()
    packet = _build(reference=reference)
    assert packet.guidance.source_id in reference.sources
