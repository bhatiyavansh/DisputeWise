"""Tests for the Phase 2 POST /cases/{case_id}/score endpoint."""

import pytest

from app.ml import schema
from tests.factories import make_case

pytest.importorskip("lightgbm")
pytest.importorskip("shap")


@pytest.fixture()
def scored(client, db_session, risk_model):
    """A stored case plus its scoring response."""
    make_case(db_session, dispute_id="DSP-000001", reason_code="goods_not_received")
    response = client.post("/cases/DSP-000001/score")
    assert response.status_code == 200, response.text
    return response.json()


def test_score_valid_case(client, db_session, risk_model):
    make_case(db_session, dispute_id="DSP-000001")
    response = client.post("/cases/DSP-000001/score")
    assert response.status_code == 200
    assert response.json()["case_id"] == "DSP-000001"


def test_score_unknown_case(client, db_session, risk_model):
    response = client.post("/cases/DSP-999999/score")
    assert response.status_code == 404


def test_score_response_schema(scored):
    expected = {
        "case_id",
        "model_version",
        "feature_schema_version",
        "reason_code",
        "raw_probability",
        "calibrated_probability",
        "risk_band",
        "calibration_method",
        "top_positive_factors",
        "top_negative_factors",
        "evidence_summary",
        "disclaimer",
    }
    assert expected <= set(scored)


def test_score_contains_model_version(scored):
    assert scored["model_version"] == schema.MODEL_VERSION
    assert scored["feature_schema_version"] == schema.FEATURE_SCHEMA_VERSION


def test_score_contains_calibrated_probability(scored):
    assert 0.0 <= scored["calibrated_probability"] <= 1.0
    assert 0.0 <= scored["raw_probability"] <= 1.0
    assert scored["calibration_method"] in {"sigmoid", "isotonic", "identity"}


def test_score_risk_band_consistent_with_probability(scored):
    assert scored["risk_band"] == schema.risk_band(scored["calibrated_probability"])
    assert scored["risk_band"] in {
        schema.RISK_BAND_HIGH,
        schema.RISK_BAND_MEDIUM,
        schema.RISK_BAND_LOW,
    }


def test_score_factors_are_shap_shaped(scored):
    for key in ("top_positive_factors", "top_negative_factors"):
        for factor in scored[key]:
            assert {"feature", "contribution", "description"} <= set(factor)
            assert isinstance(factor["description"], str) and factor["description"]
    assert all(f["contribution"] > 0 for f in scored["top_positive_factors"])
    assert all(f["contribution"] < 0 for f in scored["top_negative_factors"])


def test_score_evidence_summary(scored):
    summary = scored["evidence_summary"]
    assert {
        "total",
        "available",
        "strong",
        "high_relevance_total",
        "high_relevance_available",
        "missing_key_types",
    } <= set(summary)
    assert summary["available"] <= summary["total"]
    assert summary["high_relevance_available"] <= summary["high_relevance_total"]
    assert isinstance(summary["missing_key_types"], list)


def test_score_is_deterministic(client, db_session, risk_model):
    make_case(db_session, dispute_id="DSP-000001")
    first = client.post("/cases/DSP-000001/score").json()
    second = client.post("/cases/DSP-000001/score").json()
    assert first["calibrated_probability"] == second["calibrated_probability"]
    assert first["top_positive_factors"] == second["top_positive_factors"]


def test_score_top_n_parameter(client, db_session, risk_model):
    make_case(db_session, dispute_id="DSP-000001")
    response = client.post("/cases/DSP-000001/score", params={"top_n": 2})
    assert response.status_code == 200
    assert len(response.json()["top_positive_factors"]) <= 2


def test_score_disclaims_decisioning(scored):
    """Phase 2 must not present itself as a contest recommendation."""
    disclaimer = scored["disclaimer"].lower()
    assert "decision support" in disclaimer
    assert "not" in disclaimer


def test_score_handles_case_with_sparse_evidence(client, db_session, risk_model):
    """The factory case has a single evidence row; scoring must still work."""
    make_case(db_session, dispute_id="DSP-000042", reason_code="duplicate_charge")
    response = client.post("/cases/DSP-000042/score")
    assert response.status_code == 200
    body = response.json()
    assert body["reason_code"] == "duplicate_charge"
    assert body["evidence_summary"]["total"] == 1


# --- Phase 1 endpoints must be unaffected ----------------------------------


def test_decision_endpoint_now_implemented_by_phase_3(client, db_session):
    """Written in Phase 2 to guard that /decision was still a stub; Phase 3
    implements it (see tests/test_decision_api.py for full coverage), so this
    assertion is now inverted rather than deleted -- same pattern as
    test_score_endpoint_is_implemented_in_phase_2 in tests/test_cases.py.
    """
    make_case(db_session, dispute_id="DSP-000001")
    assert client.post("/cases/DSP-000001/decision").status_code != 501


def test_draft_endpoint_now_implemented_by_phase_4(client, db_session):
    """Written in Phase 2 to guard that /draft was still a stub; Phase 4
    implements it -- same inversion pattern as the other phase boundaries."""
    make_case(db_session, dispute_id="DSP-000001")
    assert client.post("/cases/DSP-000001/draft").status_code != 501
