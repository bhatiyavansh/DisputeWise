"""Tests for POST /cases/{case_id}/decision."""

import pytest

from app.decision.schema import DECISIONS, DECISION_POLICY_VERSION
from app.ml import schema as ml_schema
from tests.factories import make_case

pytest.importorskip("lightgbm")
pytest.importorskip("shap")


@pytest.fixture()
def decided(client, db_session, risk_model):
    make_case(db_session, dispute_id="DSP-000001", reason_code="goods_not_received")
    response = client.post("/cases/DSP-000001/decision")
    assert response.status_code == 200, response.text
    return response.json()


def test_valid_case_returns_200(client, db_session, risk_model):
    make_case(db_session, dispute_id="DSP-000001")
    response = client.post("/cases/DSP-000001/decision")
    assert response.status_code == 200
    assert response.json()["case_id"] == "DSP-000001"


def test_unknown_case_returns_404(client, db_session, risk_model):
    response = client.post("/cases/DSP-999999/decision")
    assert response.status_code == 404


def test_probability_preserved_from_phase_2(client, db_session, risk_model):
    make_case(db_session, dispute_id="DSP-000001")
    score = client.post("/cases/DSP-000001/score").json()
    decision = client.post("/cases/DSP-000001/decision").json()
    assert decision["calibrated_probability"] == score["calibrated_probability"]
    assert decision["risk_band"] == score["risk_band"]
    assert decision["model_version"] == score["model_version"]


def test_decision_value_is_valid(decided):
    assert decided["decision"] in DECISIONS


def test_response_contains_policy_version(decided):
    assert decided["decision_policy_version"] == DECISION_POLICY_VERSION
    assert decided["model_version"] == ml_schema.MODEL_VERSION
    assert decided["feature_schema_version"] == ml_schema.FEATURE_SCHEMA_VERSION


def test_response_contains_economic_breakdown(decided):
    expected_keys = {
        "calibrated_probability",
        "dispute_amount",
        "recovery_rate",
        "recoverable_amount",
        "contest_cost",
        "expected_recovery",
        "expected_net_value",
        "break_even_probability",
        "break_even_explanation",
        "sensitivity",
    }
    assert expected_keys <= set(decided)
    assert decided["expected_recovery"] == pytest.approx(
        decided["calibrated_probability"] * decided["recoverable_amount"], abs=0.01
    )
    assert decided["expected_net_value"] == pytest.approx(
        decided["expected_recovery"] - decided["contest_cost"], abs=0.01
    )


def test_response_contains_disclaimer(decided):
    disclaimer = decided["disclaimer"].lower()
    assert "decision support" in disclaimer
    assert "not" in disclaimer and "automatically" in disclaimer


def test_response_contains_evidence_and_shap(decided):
    assert "evidence_summary" in decided
    assert "top_positive_factors" in decided
    assert "top_negative_factors" in decided
    assert "reason" in decided and isinstance(decided["reason"], str) and decided["reason"]


def test_sensitivity_is_a_list_of_points(decided):
    assert isinstance(decided["sensitivity"], list)
    for point in decided["sensitivity"]:
        assert {"probability", "delta", "expected_recovery", "expected_net_value"} <= set(point)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_case_same_config_same_decision(client, db_session, risk_model):
    make_case(db_session, dispute_id="DSP-000001")
    first = client.post("/cases/DSP-000001/decision").json()
    second = client.post("/cases/DSP-000001/decision").json()
    assert first["decision"] == second["decision"]
    assert first["expected_net_value"] == second["expected_net_value"]
    assert first["reason"] == second["reason"]


def test_same_case_same_config_same_calculations(client, db_session, risk_model):
    make_case(db_session, dispute_id="DSP-000001")
    first = client.post("/cases/DSP-000001/decision").json()
    second = client.post("/cases/DSP-000001/decision").json()
    for key in ("recoverable_amount", "expected_recovery", "break_even_probability", "sensitivity"):
        assert first[key] == second[key]


# ---------------------------------------------------------------------------
# Regression: Phase 1/2 endpoints unaffected
# ---------------------------------------------------------------------------


def test_score_endpoint_unaffected(client, db_session, risk_model):
    make_case(db_session, dispute_id="DSP-000001")
    response = client.post("/cases/DSP-000001/score")
    assert response.status_code == 200


def test_draft_endpoint_now_implemented_by_phase_4(client, db_session):
    """Written in Phase 3 to guard that /draft was still a stub; Phase 4
    implements it (see tests/test_evidence_intel_api.py for full coverage),
    so this assertion is now inverted rather than deleted -- same pattern as
    the Phase 2/3 equivalents in test_cases.py / test_score_api.py.
    """
    make_case(db_session, dispute_id="DSP-000001")
    assert client.post("/cases/DSP-000001/draft").status_code != 501


def test_health_endpoint_unaffected(client):
    assert client.get("/health").status_code == 200
