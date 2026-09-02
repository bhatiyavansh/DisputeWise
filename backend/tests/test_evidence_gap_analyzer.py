"""Part A + reference-data mapping tests for the Evidence Gap Analyzer."""

import pytest

from app.evidence_intel import versions as v
from app.evidence_intel.gap_analyzer import CaseEvidenceState, analyze_gap, case_evidence_state_from_rows
from app.evidence_intel.reference_data import load_reference_data


@pytest.fixture(scope="module")
def reference():
    return load_reference_data()


# ---------------------------------------------------------------------------
# Reference-data mapping
# ---------------------------------------------------------------------------


def test_reference_data_loads_all_three_reason_codes(reference):
    assert set(reference.reason_codes) == {"unauthorized_transaction", "goods_not_received", "duplicate_charge"}


def test_reference_data_has_provenance_for_every_requirement(reference):
    for requirement in reference.evidence_requirements:
        assert reference.source(requirement.source_id) is not None, requirement.source_id


def test_unknown_reason_code_raises(reference):
    with pytest.raises(ValueError, match="no reference"):
        analyze_gap("not_a_real_reason_code", {}, reference)


# ---------------------------------------------------------------------------
# Gap analysis logic
# ---------------------------------------------------------------------------


def _all_available(reason_code: str, reference) -> dict[str, CaseEvidenceState]:
    return {
        r.evidence_type: CaseEvidenceState(evidence_type=r.evidence_type, available=True, strength=0.8, evidence_id=f"EVD-{r.evidence_type}")
        for r in reference.requirements_for(reason_code)
    }


def test_full_coverage_when_all_required_evidence_available(reference):
    state = _all_available("goods_not_received", reference)
    result = analyze_gap("goods_not_received", state, reference)
    assert result.missing_count == 0
    assert result.coverage_ratio == 1.0
    assert not result.has_critical_gap


def test_missing_high_relevance_evidence_is_critical(reference):
    state = _all_available("goods_not_received", reference)
    del state["proof_of_delivery"]  # high relevance for this reason code
    result = analyze_gap("goods_not_received", state, reference)
    assert result.has_critical_gap
    assert "proof_of_delivery" in [i.evidence_type for i in result.missing_critical]
    item = next(i for i in result.items if i.evidence_type == "proof_of_delivery")
    assert item.priority == v.PRIORITY_CRITICAL
    assert item.status == v.STATUS_MISSING


def test_missing_medium_relevance_evidence_is_important_not_critical(reference):
    state = _all_available("goods_not_received", reference)
    del state["refund_request"]  # medium relevance for this reason code
    result = analyze_gap("goods_not_received", state, reference)
    item = next(i for i in result.items if i.evidence_type == "refund_request")
    assert item.priority == v.PRIORITY_IMPORTANT
    assert not result.has_critical_gap


def test_low_relevance_evidence_not_counted_in_coverage(reference):
    """Low-relevance types are reported but excluded from the required denominator."""
    state = _all_available("goods_not_received", reference)
    result_full = analyze_gap("goods_not_received", state, reference)
    del state["avs"]  # low relevance for goods_not_received
    result_missing_low = analyze_gap("goods_not_received", state, reference)
    assert result_full.required_count == result_missing_low.required_count
    assert result_full.missing_count == result_missing_low.missing_count
    low_item = next(i for i in result_missing_low.items if i.evidence_type == "avs")
    assert low_item.required is False
    assert low_item.priority == v.PRIORITY_NONE


def test_absent_evidence_type_treated_as_missing(reference):
    """An evidence_type with no row at all is MISSING, same as available=False."""
    result = analyze_gap("goods_not_received", {}, reference)
    assert result.missing_count == result.required_count
    assert all(i.status == v.STATUS_MISSING for i in result.items if i.required)


def test_every_reason_code_has_a_gap_analysis(reference):
    for reason_code in reference.reason_codes:
        result = analyze_gap(reason_code, {}, reference)
        assert result.required_count > 0
        assert result.reason_code == reason_code


def test_reason_code_specific_relevance_differs():
    """The same evidence_type has different relevance for different reason
    codes -- proves the analyzer is genuinely reason-code-aware, not just
    returning a fixed evidence list."""
    reference = load_reference_data()
    three_ds_for_fraud = next(
        r for r in reference.requirements_for("unauthorized_transaction") if r.evidence_type == "three_ds"
    )
    three_ds_for_delivery = next(
        r for r in reference.requirements_for("goods_not_received") if r.evidence_type == "three_ds"
    )
    assert three_ds_for_fraud.relevance == "high"
    assert three_ds_for_delivery.relevance == "low"


def test_provenance_present_on_every_gap_item(reference):
    state = _all_available("unauthorized_transaction", reference)
    result = analyze_gap("unauthorized_transaction", state, reference)
    for item in result.items:
        assert item.source_id
        assert reference.source(item.source_id) is not None
        assert item.reason  # non-empty description


def test_gap_analysis_deterministic(reference):
    state = _all_available("duplicate_charge", reference)
    first = analyze_gap("duplicate_charge", state, reference)
    second = analyze_gap("duplicate_charge", state, reference)
    assert first == second


# ---------------------------------------------------------------------------
# ORM-row adapter
# ---------------------------------------------------------------------------


class _FakeRow:
    def __init__(self, evidence_type, available, strength, evidence_id):
        self.evidence_type = evidence_type
        self.available = available
        self.strength = strength
        self.evidence_id = evidence_id


def test_case_evidence_state_from_rows():
    rows = [_FakeRow("proof_of_delivery", True, 0.75, "EVD-1"), _FakeRow("avs", False, 0.0, "EVD-2")]
    state = case_evidence_state_from_rows(rows)
    assert state["proof_of_delivery"].available is True
    assert state["proof_of_delivery"].strength == 0.75
    assert state["avs"].available is False
