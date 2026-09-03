"""Phase 7A -- POST /cases/{id}/evidence-scenario.

Covers: both sides genuinely recompute through the real pipeline, the
stored case is unmodified, nothing is persisted, no target field is
accepted, and the "not a causal estimate" disclaimer is always present.
"""

import pytest

from app.ml import schema as ml_schema
from tests.factories import add_evidence, make_case

pytest.importorskip("lightgbm")
pytest.importorskip("shap")


@pytest.fixture()
def case_with_gap(db_session):
    """A goods-not-received case missing proof_of_delivery -- the same shape
    as the real dataset case used in the demo."""
    dispute = make_case(db_session, dispute_id="DSP-000042", reason_code="goods_not_received")
    add_evidence(
        db_session, dispute, evidence_type="delivery_timestamp", available=True,
        value={"timestamp": "2026-01-05T00:00:00+00:00"}, relevance="high", strength=0.8,
        evidence_id="EVD-TS-042",
    )
    add_evidence(
        db_session, dispute, evidence_type="tracking_available", available=True,
        value={"available": True}, relevance="high", strength=0.8, evidence_id="EVD-TRK-042",
    )
    add_evidence(
        db_session, dispute, evidence_type="proof_of_delivery", available=False, value=None,
        relevance="high", strength=0.0, evidence_id="EVD-POD-042",
    )
    return dispute


def _scenario(client, case_id="DSP-000042", **body):
    return client.post(f"/cases/{case_id}/evidence-scenario", json=body)


# ---------------------------------------------------------------------------
# Valid scenario / recomputation
# ---------------------------------------------------------------------------


def test_valid_scenario_returns_both_sides(client, case_with_gap, risk_model):
    resp = _scenario(client, add_evidence=["proof_of_delivery"])
    assert resp.status_code == 200
    body = resp.json()

    assert body["case_id"] == "DSP-000042"
    assert body["is_scenario"] is True
    assert body["evidence_added"] == ["proof_of_delivery"]
    assert "current" in body and "scenario" in body


def test_probability_actually_recomputes(client, case_with_gap, risk_model):
    """Adding corroborating evidence must produce a genuinely different
    model evaluation, not a copied number."""
    body = _scenario(client, add_evidence=["proof_of_delivery"]).json()
    current = body["current"]["score"]["calibrated_probability"]
    scenario = body["scenario"]["score"]["calibrated_probability"]

    assert current != scenario
    assert body["delta"]["calibrated_probability"] == pytest.approx(scenario - current, abs=1e-6)


def test_decision_actually_recomputes(client, case_with_gap, risk_model):
    body = _scenario(client, add_evidence=["proof_of_delivery"]).json()
    assert body["delta"]["decision_from"] == body["current"]["decision"]["decision"]
    assert body["delta"]["decision_to"] == body["scenario"]["decision"]["decision"]
    assert body["delta"]["decision_changed"] == (
        body["delta"]["decision_from"] != body["delta"]["decision_to"]
    )


def test_evidence_gap_recomputes_and_resolves_the_critical_gap(client, case_with_gap, risk_model):
    body = _scenario(client, add_evidence=["proof_of_delivery"]).json()

    def critical_missing(side):
        return {
            item["evidence_type"]
            for item in body[side]["evidence_gap"]["items"]
            if item["priority"] == "CRITICAL" and item["status"] == "MISSING"
        }

    assert "proof_of_delivery" in critical_missing("current")
    assert "proof_of_delivery" not in critical_missing("scenario")
    assert body["delta"]["critical_gaps_resolved"] == ["proof_of_delivery"]
    assert body["scenario"]["evidence_gap"]["coverage_ratio"] > body["current"]["evidence_gap"]["coverage_ratio"]


def test_removing_evidence_introduces_a_gap(client, case_with_gap, risk_model):
    body = _scenario(client, remove_evidence=["tracking_available"]).json()
    assert "tracking_available" in body["delta"]["critical_gaps_introduced"]
    assert body["scenario"]["evidence_gap"]["coverage_ratio"] < body["current"]["evidence_gap"]["coverage_ratio"]


def test_current_side_matches_the_plain_score_endpoint(client, case_with_gap, risk_model):
    """The 'current' side is the real case, evaluated by the same path the
    normal /score endpoint uses -- not a separate calculation."""
    scenario_body = _scenario(client, add_evidence=["proof_of_delivery"]).json()
    score_body = client.post("/cases/DSP-000042/score").json()

    assert scenario_body["current"]["score"]["calibrated_probability"] == pytest.approx(
        score_body["calibrated_probability"], abs=1e-9
    )


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------


def test_invalid_evidence_type_rejected(client, case_with_gap, risk_model):
    resp = _scenario(client, add_evidence=["not_a_real_evidence_type"])
    assert resp.status_code == 422
    assert "unknown evidence types" in resp.text


def test_empty_scenario_rejected(client, case_with_gap, risk_model):
    resp = _scenario(client)
    assert resp.status_code == 422


def test_contradictory_scenario_rejected(client, case_with_gap, risk_model):
    resp = _scenario(client, add_evidence=["proof_of_delivery"], remove_evidence=["proof_of_delivery"])
    assert resp.status_code == 422


def test_unknown_case_returns_404(client, db_session, risk_model):
    resp = _scenario(client, case_id="DSP-999999", add_evidence=["proof_of_delivery"])
    assert resp.status_code == 404


@pytest.mark.parametrize("target_field", sorted(ml_schema.FORBIDDEN_COLUMNS))
def test_no_target_field_accepted(client, case_with_gap, target_field, risk_model):
    resp = _scenario(client, add_evidence=["proof_of_delivery"], **{target_field: 1})
    assert resp.status_code == 422, f"{target_field} must be rejected"


def test_unknown_field_rejected(client, case_with_gap, risk_model):
    resp = _scenario(client, add_evidence=["proof_of_delivery"], some_future_field=1)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# No mutation / no persistence
# ---------------------------------------------------------------------------


def test_stored_case_is_unchanged_by_a_scenario(client, case_with_gap, db_session, risk_model):
    from app.models import Evidence

    def pod_row():
        db_session.expire_all()
        return db_session.query(Evidence).filter_by(evidence_id="EVD-POD-042").one()

    before = (pod_row().available, pod_row().strength, pod_row().value)
    assert _scenario(client, add_evidence=["proof_of_delivery"]).status_code == 200
    after = (pod_row().available, pod_row().strength, pod_row().value)

    assert before == after
    assert after[0] is False  # still genuinely missing


def test_scenario_does_not_create_rows(client, case_with_gap, db_session, risk_model):
    from app.models import Customer, Dispute, Evidence, Transaction

    counts = lambda: {  # noqa: E731
        m.__name__: db_session.query(m).count() for m in (Dispute, Transaction, Customer, Evidence)
    }
    before = counts()
    assert _scenario(client, add_evidence=["proof_of_delivery", "customer_communication_available"]).status_code == 200
    db_session.expire_all()
    assert counts() == before


def test_score_after_scenario_is_unchanged(client, case_with_gap, risk_model):
    """End-to-end proof the production case is untouched: its own score is
    identical before and after a scenario ran against it."""
    before = client.post("/cases/DSP-000042/score").json()["calibrated_probability"]
    _scenario(client, add_evidence=["proof_of_delivery"])
    after = client.post("/cases/DSP-000042/score").json()["calibrated_probability"]
    assert before == after


# ---------------------------------------------------------------------------
# Labelling / provenance
# ---------------------------------------------------------------------------


def test_response_is_labelled_scenario_and_not_causal(client, case_with_gap, risk_model):
    body = _scenario(client, add_evidence=["proof_of_delivery"]).json()
    assert body["is_scenario"] is True
    assert body["persisted"] is False
    assert "not a causal estimate" in body["disclaimer"]


def test_version_metadata_present(client, case_with_gap, risk_model):
    body = _scenario(client, add_evidence=["proof_of_delivery"]).json()
    assert body["model_version"] == "risk-v1"
    assert body["feature_schema_version"] == "features-v1"
    assert body["decision_policy_version"] == "decision-v1"
    assert body["evidence_schema_version"] == "evidence-v1"
    assert body["generated_at"]


def test_supported_evidence_types_cover_the_documented_toggles(client, case_with_gap, risk_model):
    """Every evidence type the UI offers must actually be accepted."""
    for evidence_type in [
        "proof_of_delivery",
        "tracking_available",
        "delivery_address_match",
        "delivery_confirmed",
        "three_ds",
        "avs",
        "cvv",
        "customer_communication_available",
    ]:
        resp = _scenario(client, add_evidence=[evidence_type])
        assert resp.status_code == 200, f"{evidence_type} should be toggleable"
