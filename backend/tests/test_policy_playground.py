"""Phase 7B -- decision policy playground.

Covers: the default playground run reproduces decision-v1 exactly, parameter
changes actually re-route the portfolio, invalid values are rejected by
decision-v1's own validators, and the production configuration is never
mutated.

These tests run against the validation split (never the locked test set --
see app/services/portfolio_service.py for why) and are skipped when the
dataset or model artifacts are not present in a checkout.
"""

import pytest

pytest.importorskip("lightgbm")
pytest.importorskip("shap")


@pytest.fixture(scope="module", autouse=True)
def _require_portfolio(risk_model):
    """Skip the module cleanly if the split CSVs aren't generated."""
    from app.services.portfolio_service import get_scored_portfolio

    try:
        get_scored_portfolio(risk_model)
    except FileNotFoundError as exc:
        pytest.skip(f"dataset split not generated: {exc}")


def _simulate(client, **overrides):
    return client.post("/policy/simulate", json=overrides)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_policy_defaults_endpoint_reports_decision_v1(client):
    body = client.get("/policy/default").json()
    assert body["decision_policy_version"] == "decision-v1"
    assert body["defaults"]["contest_cost"] == 300.0
    assert body["defaults"]["recovery_rate"] == 1.0
    assert body["defaults"]["high_confidence_probability"] == 0.65
    assert set(body["tunable_fields"]) == {
        "contest_cost",
        "recovery_rate",
        "high_confidence_probability",
        "low_confidence_probability",
        "min_expected_net_value",
        "review_margin",
    }


def test_default_playground_run_matches_decision_v1(client, risk_model):
    """With no overrides the scenario policy IS the production policy, so
    both routings must be identical -- proof the playground evaluates through
    the real engine rather than an approximation of it."""
    body = _simulate(client).json()

    assert body["changed_fields"] == []
    assert body["default_config"] == body["scenario_config"]
    assert body["scenario_policy"]["buckets"] == body["default_policy"]["buckets"]


def test_response_is_labelled_a_simulation_on_validation(client, risk_model):
    body = _simulate(client).json()
    assert body["is_simulation"] is True
    assert body["split"] == "validation"
    assert body["n_cases"] > 0
    assert "PROTOTYPE ASSUMPTIONS" in body["note"]
    assert "retrospective" in body["note"].lower()


# ---------------------------------------------------------------------------
# Parameters actually change routing / economics
# ---------------------------------------------------------------------------


def test_raising_contest_cost_changes_economics(client, risk_model):
    body = _simulate(client, contest_cost=5000).json()

    assert body["changed_fields"] == ["contest_cost"]
    default_env = body["default_policy"]["portfolio"]["contest_only_expected_net_value"]
    scenario_env = body["scenario_policy"]["portfolio"]["contest_only_expected_net_value"]
    assert scenario_env != default_env


def test_raising_confidence_threshold_reduces_contest_volume(client, risk_model):
    """A stricter confidence requirement can only shrink the CONTEST bucket."""
    body = _simulate(client, high_confidence_probability=0.95).json()

    default_contest = body["default_policy"]["buckets"]["CONTEST"]["count"]
    scenario_contest = body["scenario_policy"]["buckets"]["CONTEST"]["count"]
    assert scenario_contest < default_contest


def test_lowering_confidence_threshold_increases_contest_volume(client, risk_model):
    body = _simulate(client, high_confidence_probability=0.40).json()

    default_contest = body["default_policy"]["buckets"]["CONTEST"]["count"]
    scenario_contest = body["scenario_policy"]["buckets"]["CONTEST"]["count"]
    assert scenario_contest > default_contest


def test_recovery_rate_scales_expected_recovery(client, risk_model):
    body = _simulate(client, recovery_rate=0.5).json()
    default_recovery = body["default_policy"]["buckets"]["CONTEST"]["expected_recovery_total"]
    scenario_recovery = body["scenario_policy"]["buckets"]["CONTEST"]["expected_recovery_total"]
    assert scenario_recovery < default_recovery


def test_bucket_percentages_sum_to_100(client, risk_model):
    buckets = _simulate(client).json()["scenario_policy"]["buckets"]
    total = sum(b["percentage"] for b in buckets.values())
    assert total == pytest.approx(100.0, abs=0.1)


# ---------------------------------------------------------------------------
# The contest-everything finding is surfaced, not hidden
# ---------------------------------------------------------------------------


def test_contest_everything_baseline_is_reported(client, risk_model):
    """At the prototype contest cost this baseline can out-earn the default
    policy on realized value. The playground must show it rather than hide
    the sensitivity."""
    body = _simulate(client).json()
    baseline = body["contest_everything_baseline"]

    assert baseline["buckets"]["CONTEST"]["count"] == body["n_cases"]
    assert baseline["portfolio"]["contest_only_realized_net_value"] is not None


def test_model_separates_buckets_by_actual_outcome(client, risk_model):
    """Sanity check on the retrospective numbers: the CONTEST bucket should
    have a materially higher favorable rate than DO_NOT_CONTEST. Asserted as
    an ordering, not a target value -- nothing here is tuned."""
    buckets = _simulate(client).json()["default_policy"]["buckets"]
    assert (
        buckets["CONTEST"]["actual_favorable_outcome_rate"]
        > buckets["DO_NOT_CONTEST"]["actual_favorable_outcome_rate"]
    )


# ---------------------------------------------------------------------------
# Invalid input, rejected by decision-v1's own validators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"contest_cost": -1},
        {"recovery_rate": 1.5},
        {"recovery_rate": -0.1},
        {"high_confidence_probability": 1.4},
        {"review_margin": -5},
        # high must remain strictly greater than low
        {"high_confidence_probability": 0.2, "low_confidence_probability": 0.8},
    ],
)
def test_invalid_policy_values_rejected(client, overrides, risk_model):
    assert _simulate(client, **overrides).status_code == 422


def test_unknown_policy_field_rejected(client, risk_model):
    assert _simulate(client, not_a_policy_field=1).status_code == 422


def test_evidence_gate_is_not_tunable(client, risk_model):
    """The evidence gate is part of decision-v1's safety behavior, not an
    economic dial -- it must not be overridable from the playground."""
    assert _simulate(client, require_high_relevance_evidence_for_contest=False).status_code == 422


# ---------------------------------------------------------------------------
# No mutation of production policy or data
# ---------------------------------------------------------------------------


def test_production_config_unchanged_after_simulation(client, risk_model):
    from app.decision.config import get_decision_config

    before = get_decision_config().model_dump()
    assert _simulate(client, contest_cost=9999, recovery_rate=0.1).status_code == 200
    after = get_decision_config().model_dump()

    assert before == after
    assert after["contest_cost"] == 300.0


def test_default_routing_is_stable_across_scenario_runs(client, risk_model):
    """Running wild scenarios must not disturb the production baseline."""
    first = _simulate(client).json()["default_policy"]["buckets"]
    _simulate(client, contest_cost=50000, high_confidence_probability=0.99)
    second = _simulate(client).json()["default_policy"]["buckets"]
    assert first == second


def test_playground_does_not_touch_the_database(client, db_session, risk_model):
    from app.models import Dispute, Evidence

    before = (db_session.query(Dispute).count(), db_session.query(Evidence).count())
    assert _simulate(client, contest_cost=1234).status_code == 200
    db_session.expire_all()
    assert (db_session.query(Dispute).count(), db_session.query(Evidence).count()) == before


def test_playground_never_uses_the_locked_test_split(client, risk_model):
    body = _simulate(client).json()
    assert body["split"] != "test"
