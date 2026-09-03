"""Phase 6 -- POST /simulate.

Covers the simulation contract: it runs the real pipeline (not a parallel
implementation), it accepts no target/outcome field, it persists nothing,
and its version metadata reports only stages that actually ran.

The three scenario tests at the bottom assert the *mechanism* (an
evidence-gap downgrade happens, weak economics produce a negative expected
net value), not hardcoded probabilities -- nothing here is tuned to make the
model or the policy look good, and none of it would need editing if the
model were retrained.
"""

import pytest

from app.api.drafts import get_optional_llm_provider
from app.evidence_intel.llm_provider import FakeLLMProvider
from app.main import app
from app.ml import schema as ml_schema

pytest.importorskip("lightgbm")
pytest.importorskip("shap")


STRONG_CASE = {
    "reason_code": "goods_not_received",
    "dispute_amount": 25000,
    "transaction_amount": 25000,
    "three_ds_authenticated": True,
    "avs_result": "Y",
    "cvv_result": "M",
    "device_match": True,
    "ip_match": True,
    "delivery_confirmed": True,
    "tracking_available": True,
    "delivery_address_match": True,
    "proof_of_delivery": True,
    "customer_communication_available": True,
    "account_age_days": 400,
    "previous_order_count": 12,
    "previous_successful_order_count": 12,
}

WEAK_CASE = {
    "reason_code": "unauthorized_transaction",
    "dispute_amount": 800,
    "transaction_amount": 800,
    "three_ds_authenticated": False,
    "avs_result": "N",
    "cvv_result": "N",
    "device_match": False,
    "ip_match": False,
    "account_age_days": 5,
    "previous_order_count": 0,
    "previous_successful_order_count": 0,
    "previous_dispute_count": 3,
}


@pytest.fixture(autouse=True)
def _clear_llm_override():
    yield
    app.dependency_overrides.pop(get_optional_llm_provider, None)


@pytest.fixture()
def no_llm(client):
    """Simulation with generation explicitly unavailable -- the default state
    for every test that isn't specifically about generation."""
    app.dependency_overrides[get_optional_llm_provider] = lambda: None
    return client


# ---------------------------------------------------------------------------
# Valid simulation / pipeline wiring
# ---------------------------------------------------------------------------


def test_valid_simulation_returns_200_with_every_stage(no_llm, risk_model):
    resp = no_llm.post("/simulate", json=STRONG_CASE)
    assert resp.status_code == 200
    body = resp.json()

    assert body["is_simulation"] is True
    assert body["simulation_id"].startswith("SIM-")
    # every pipeline stage present
    assert 0.0 <= body["score"]["calibrated_probability"] <= 1.0
    assert body["decision"]["decision"] in {"CONTEST", "HUMAN_REVIEW", "DO_NOT_CONTEST"}
    assert body["evidence_gap"]["coverage"]["required"] > 0
    assert len(body["retrieved_sources"]) > 0


def test_model_scoring_actually_invoked(no_llm, risk_model):
    """SHAP factors and a calibrated/raw probability pair can only come from
    the real model -- not from a stub."""
    body = no_llm.post("/simulate", json=STRONG_CASE).json()
    score = body["score"]
    assert score["raw_probability"] != score["calibrated_probability"] or score["calibration_method"]
    assert len(score["top_positive_factors"]) > 0
    assert all("feature" in f and "contribution" in f for f in score["top_positive_factors"])


def test_decision_engine_actually_invoked(no_llm, risk_model):
    body = no_llm.post("/simulate", json=STRONG_CASE).json()
    decision = body["decision"]
    assert decision["decision_policy_version"] == "decision-v1"
    assert decision["break_even_explanation"]
    assert len(decision["sensitivity"]) > 0
    # economics are internally consistent -- produced by the engine, not assembled here
    assert decision["expected_net_value"] == pytest.approx(
        decision["expected_recovery"] - decision["contest_cost"], abs=0.01
    )


def test_evidence_gap_actually_invoked(no_llm, risk_model):
    body = no_llm.post("/simulate", json=STRONG_CASE).json()
    gap = body["evidence_gap"]
    assert gap["reason_code"] == "goods_not_received"
    assert gap["schema_version"] == "evidence-v1"
    assert all(item["source_id"] for item in gap["items"])  # reference-data provenance


def test_retrieval_actually_invoked_with_provenance(no_llm, risk_model):
    body = no_llm.post("/simulate", json=STRONG_CASE).json()
    for source in body["retrieved_sources"]:
        assert source["source_id"]
        assert source["chunk_id"]
        assert source["text"]
        assert 0.0 <= source["relevance_score"] <= 1.0


def test_evidence_relevance_comes_from_reference_data_not_the_request(no_llm, risk_model):
    """The same evidence type carries different relevance under different
    reason codes -- proof that relevance is read from data/reference/ rather
    than invented per simulation."""
    gnr = no_llm.post("/simulate", json=STRONG_CASE).json()["evidence_gap"]
    unauth = no_llm.post("/simulate", json={**STRONG_CASE, "reason_code": "unauthorized_transaction"}).json()[
        "evidence_gap"
    ]

    def relevance_of(gap, evidence_type):
        return next(i["relevance"] for i in gap["items"] if i["evidence_type"] == evidence_type)

    assert relevance_of(gnr, "proof_of_delivery") == "HIGH"
    assert relevance_of(unauth, "proof_of_delivery") == "LOW"


# ---------------------------------------------------------------------------
# Leakage: no target/outcome field is accepted
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target_field", sorted(ml_schema.FORBIDDEN_COLUMNS))
def test_no_target_or_outcome_field_is_accepted(no_llm, target_field, risk_model):
    resp = no_llm.post("/simulate", json={**STRONG_CASE, target_field: 1})
    assert resp.status_code == 422, f"{target_field} must be rejected, not ignored"


def test_target_field_rejection_names_the_field(no_llm, risk_model):
    resp = no_llm.post("/simulate", json={**STRONG_CASE, "favorable_outcome": True})
    assert resp.status_code == 422
    assert "favorable_outcome" in resp.text


def test_unknown_field_is_rejected_not_silently_ignored(no_llm, risk_model):
    resp = no_llm.post("/simulate", json={**STRONG_CASE, "some_future_field": 3})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Invalid / missing input
# ---------------------------------------------------------------------------


def test_missing_required_fields_rejected(no_llm):
    resp = no_llm.post("/simulate", json={"reason_code": "goods_not_received"})
    assert resp.status_code == 422


def test_unknown_reason_code_rejected(no_llm):
    resp = no_llm.post("/simulate", json={**STRONG_CASE, "reason_code": "not_a_reason_code"})
    assert resp.status_code == 422


def test_non_positive_amount_rejected(no_llm):
    resp = no_llm.post("/simulate", json={**STRONG_CASE, "dispute_amount": 0})
    assert resp.status_code == 422


def test_unknown_evidence_type_rejected(no_llm):
    resp = no_llm.post("/simulate", json={**STRONG_CASE, "evidence_not_on_file": ["not_an_evidence_type"]})
    assert resp.status_code == 422
    assert "unknown evidence types" in resp.text


def test_contradictory_evidence_overrides_rejected(no_llm):
    resp = no_llm.post(
        "/simulate",
        json={**STRONG_CASE, "evidence_on_file": ["proof_of_delivery"], "evidence_not_on_file": ["proof_of_delivery"]},
    )
    assert resp.status_code == 422


def test_successful_orders_cannot_exceed_total_orders(no_llm):
    resp = no_llm.post(
        "/simulate", json={**STRONG_CASE, "previous_order_count": 2, "previous_successful_order_count": 9}
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Persistence: none
# ---------------------------------------------------------------------------


def test_simulation_persists_nothing(no_llm, db_session, risk_model):
    from app.models import Customer, Dispute, Evidence, Transaction

    before = {
        model.__name__: db_session.query(model).count()
        for model in (Dispute, Transaction, Customer, Evidence)
    }
    assert no_llm.post("/simulate", json=STRONG_CASE).status_code == 200
    db_session.expire_all()
    after = {
        model.__name__: db_session.query(model).count()
        for model in (Dispute, Transaction, Customer, Evidence)
    }
    assert before == after


def test_response_declares_it_was_not_persisted(no_llm, risk_model):
    body = no_llm.post("/simulate", json=STRONG_CASE).json()
    assert body["trace"]["persisted"] is False
    assert body["is_simulation"] is True
    assert "not persisted" in body["disclaimer"]


def test_simulation_service_takes_no_db_session():
    """Structural guarantee: the service cannot write because it has no
    Session parameter and imports no ORM model."""
    import inspect

    from app.services import simulation_service

    params = inspect.signature(simulation_service.run_simulation).parameters
    assert not any("db" in name or "session" in name for name in params)

    # No ORM model or Session is imported into the module's namespace, so
    # there is literally no handle it could persist through.
    namespace = vars(simulation_service)
    assert "Session" not in namespace
    assert not any(
        getattr(value, "__module__", "").startswith("app.models") for value in namespace.values()
    )


# ---------------------------------------------------------------------------
# Determinism + version metadata
# ---------------------------------------------------------------------------


def test_simulation_is_deterministic_for_identical_input(no_llm, risk_model):
    first = no_llm.post("/simulate", json=STRONG_CASE).json()
    second = no_llm.post("/simulate", json=STRONG_CASE).json()

    assert first["score"] == second["score"]
    assert first["decision"] == second["decision"]
    assert first["retrieved_sources"] == second["retrieved_sources"]
    # the gap analysis is identical apart from the per-run scenario label
    assert {k: v for k, v in first["evidence_gap"].items() if k != "case_id"} == {
        k: v for k, v in second["evidence_gap"].items() if k != "case_id"
    }
    # only the identifiers/timestamps differ between runs
    assert first["simulation_id"] != second["simulation_id"]


def test_trace_reports_versions_for_stages_that_ran(no_llm, risk_model):
    trace = no_llm.post("/simulate", json=STRONG_CASE).json()["trace"]
    assert trace["model_version"] == "risk-v1"
    assert trace["feature_schema_version"] == "features-v1"
    assert trace["decision_policy_version"] == "decision-v1"
    assert trace["evidence_schema_version"] == "evidence-v1"
    assert trace["knowledge_base_version"] == "knowledge-v1"
    assert trace["retrieval_config_version"] == "retrieval-v1"
    assert trace["retrieved_source_ids"]
    assert trace["generated_at"]


def test_trace_omits_generation_versions_when_generation_did_not_run(no_llm, risk_model):
    """Version metadata must describe what actually happened -- reporting a
    prompt/verifier version for a run with no generation would be fiction."""
    body = no_llm.post("/simulate", json=STRONG_CASE).json()
    assert body["generation"] is None
    assert body["trace"]["prompt_version"] is None
    assert body["trace"]["response_schema_version"] is None
    assert body["trace"]["verifier_version"] is None


# ---------------------------------------------------------------------------
# Generation stage
# ---------------------------------------------------------------------------


def test_generation_unavailable_is_handled_safely(client, risk_model):
    app.dependency_overrides[get_optional_llm_provider] = lambda: None
    body = client.post("/simulate", json={**STRONG_CASE, "generate_response": True}).json()

    assert body["generation"]["response_state"] == "GENERATION_UNAVAILABLE"
    assert body["generation"]["generation_available"] is False
    assert body["generation"]["response_body"] is None
    # the deterministic stages are still fully returned
    assert body["score"]["calibrated_probability"] >= 0
    assert body["evidence_gap"]["coverage"]["required"] > 0


def test_generation_runs_through_the_real_verifier(client, risk_model):
    def _fake_provider():
        return FakeLLMProvider(
            response={
                "summary": "Delivery is documented.",
                "claims": [
                    {
                        "claim_id": "C1",
                        "text": "Delivery was confirmed.",
                        "claim_type": "fact",
                        "evidence_ids": [],
                        "source_ids": ["stripe_dispute_reason_codes_2026"],
                    }
                ],
                "missing_evidence": [],
                "response_body": "Delivery was confirmed.",
            }
        )

    app.dependency_overrides[get_optional_llm_provider] = _fake_provider
    body = client.post("/simulate", json={**STRONG_CASE, "generate_response": True}).json()

    generation = body["generation"]
    assert generation["generation_available"] is True
    # one verification per claim + the verifier-v1.1 RESPONSE_BODY check
    ids = {c["claim_id"] for c in generation["claim_verifications"]}
    assert ids == {"C1", "RESPONSE_BODY"}
    assert body["trace"]["verifier_version"] == "verifier-v1.1"
    assert body["trace"]["prompt_version"] == "prompt-v1.1"


def test_verifier_blocks_a_claim_citing_evidence_that_is_not_on_file(client, risk_model):
    """The verifier stays authoritative in simulation exactly as it is for a
    stored case -- an invented evidence reference is not accepted."""

    def _fake_provider():
        return FakeLLMProvider(
            response={
                "summary": "s",
                "claims": [
                    {
                        "claim_id": "C1",
                        "text": "Proof of delivery is on file.",
                        "claim_type": "fact",
                        "evidence_ids": ["EVD-DOES-NOT-EXIST"],
                        "source_ids": [],
                    }
                ],
                "missing_evidence": [],
                "response_body": "Proof of delivery is on file.",
            }
        )

    app.dependency_overrides[get_optional_llm_provider] = _fake_provider
    body = client.post(
        "/simulate",
        json={**STRONG_CASE, "proof_of_delivery": False, "generate_response": True},
    ).json()

    generation = body["generation"]
    assert generation["response_state"] == "DRAFT_BLOCKED"
    statuses = {c["claim_id"]: c["status"] for c in generation["claim_verifications"]}
    assert statuses["C1"] in {"UNSUPPORTED", "INVALID_REFERENCE"}


# ---------------------------------------------------------------------------
# The three required scenarios
# ---------------------------------------------------------------------------


def test_scenario_strong_evidence_contests(no_llm, risk_model):
    body = no_llm.post("/simulate", json=STRONG_CASE).json()
    assert body["decision"]["decision"] == "CONTEST"
    assert body["decision"]["expected_net_value"] > 0
    assert body["evidence_gap"]["coverage_ratio"] == 1.0


def test_scenario_high_probability_but_critical_gap_goes_to_human_review(no_llm, risk_model):
    """The product's core claim: high winnability alone does not mean
    contest. Same case as STRONG_CASE with proof_of_delivery missing."""
    strong = no_llm.post("/simulate", json=STRONG_CASE).json()
    gapped = no_llm.post("/simulate", json={**STRONG_CASE, "proof_of_delivery": False}).json()

    # still a high-probability, economically positive case ...
    assert gapped["score"]["calibrated_probability"] > 0.5
    assert gapped["decision"]["expected_net_value"] > 0
    # ... but routed to a human because a CRITICAL gap exists
    assert gapped["decision"]["decision"] == "HUMAN_REVIEW"
    assert gapped["decision"]["evidence_gap_downgrade"] is True
    assert strong["decision"]["decision"] == "CONTEST"

    critical = [
        item["evidence_type"]
        for item in gapped["evidence_gap"]["items"]
        if item["priority"] == "CRITICAL" and item["status"] == "MISSING"
    ]
    assert "proof_of_delivery" in critical


def test_scenario_weak_case_does_not_contest(no_llm, risk_model):
    body = no_llm.post("/simulate", json=WEAK_CASE).json()
    assert body["decision"]["decision"] == "DO_NOT_CONTEST"
    assert body["decision"]["expected_net_value"] < 0
