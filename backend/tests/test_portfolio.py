"""Phase 7C -- GET /portfolio/summary.

Covers aggregation correctness against independently recomputed values, that
every reported figure is derived from real data rather than invented, and
that the view uses the production policy and never the locked test split.
"""

import pytest

pytest.importorskip("lightgbm")
pytest.importorskip("shap")


@pytest.fixture()
def summary(client, risk_model):
    from app.services.portfolio_service import get_scored_portfolio

    try:
        get_scored_portfolio(risk_model)
    except FileNotFoundError as exc:
        pytest.skip(f"dataset split not generated: {exc}")

    resp = client.get("/portfolio/summary")
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture()
def portfolio(risk_model):
    from app.services.portfolio_service import get_scored_portfolio

    try:
        return get_scored_portfolio(risk_model)
    except FileNotFoundError as exc:
        pytest.skip(f"dataset split not generated: {exc}")


# ---------------------------------------------------------------------------
# Counts and totals match the underlying data
# ---------------------------------------------------------------------------


def test_case_count_matches_the_split(summary, portfolio):
    assert summary["n_cases"] == portfolio.n_cases


def test_total_disputed_amount_matches_the_split(summary, portfolio):
    assert summary["total_disputed_amount"] == pytest.approx(float(portfolio.dispute_amount.sum()), abs=0.01)


def test_decision_counts_sum_to_the_case_count(summary):
    assert sum(b["count"] for b in summary["decisions"]) == summary["n_cases"]


def test_decision_percentages_sum_to_100(summary):
    assert sum(b["percentage"] for b in summary["decisions"]) == pytest.approx(100.0, abs=0.1)


def test_decision_amounts_sum_to_total_disputed(summary):
    total = sum(b["total_amount"] for b in summary["decisions"])
    assert total == pytest.approx(summary["total_disputed_amount"], rel=1e-6)


def test_all_three_decision_buckets_present(summary):
    assert {b["decision"] for b in summary["decisions"]} == {
        "CONTEST",
        "HUMAN_REVIEW",
        "DO_NOT_CONTEST",
    }


def test_reason_code_counts_sum_to_the_case_count(summary):
    assert sum(g["count"] for g in summary["by_reason_code"]) == summary["n_cases"]


def test_reason_codes_are_the_real_taxonomy(summary):
    assert {g["key"] for g in summary["by_reason_code"]} <= {
        "unauthorized_transaction",
        "goods_not_received",
        "duplicate_charge",
    }


def test_probability_bands_partition_the_portfolio(summary):
    assert sum(g["count"] for g in summary["by_probability_band"]) == summary["n_cases"]


def test_evidence_completeness_bands_partition_the_portfolio(summary):
    assert sum(g["count"] for g in summary["by_evidence_completeness"]) == summary["n_cases"]


def test_missing_evidence_count_matches_the_split(summary, portfolio):
    assert summary["cases_with_missing_high_relevance_evidence"] == int(portfolio.missing_high_relevance.sum())


def test_mean_probability_matches_the_split(summary, portfolio):
    assert summary["mean_calibrated_probability"] == pytest.approx(
        float(portfolio.calibrated_probability.mean()), abs=1e-4
    )


# ---------------------------------------------------------------------------
# Economics are internally consistent
# ---------------------------------------------------------------------------


def test_expected_recovery_never_exceeds_disputed_amount(summary):
    """With recovery_rate <= 1 and probability <= 1 this must hold."""
    assert summary["total_expected_recovery"] <= summary["total_disputed_amount"] + 0.01


def test_contest_only_figures_are_bounded_by_portfolio_totals(summary):
    assert summary["contest_only_expected_net_value"] <= summary["total_expected_net_value"] + 0.01


def test_evidence_gap_downgrades_only_appear_in_human_review(summary):
    """The gate only ever downgrades CONTEST -> HUMAN_REVIEW, so no other
    bucket can contain a downgraded case."""
    by_decision = {b["decision"]: b for b in summary["decisions"]}
    assert by_decision["CONTEST"]["evidence_gap_downgrades"] == 0
    assert by_decision["DO_NOT_CONTEST"]["evidence_gap_downgrades"] == 0
    assert by_decision["HUMAN_REVIEW"]["evidence_gap_downgrades"] > 0


def test_favorable_rate_ordering_is_sane(summary):
    """Retrospective check that routing tracks reality. An ordering, not a
    target -- nothing is tuned to satisfy this."""
    by_decision = {b["decision"]: b for b in summary["decisions"]}
    assert (
        by_decision["CONTEST"]["actual_favorable_outcome_rate"]
        > by_decision["DO_NOT_CONTEST"]["actual_favorable_outcome_rate"]
    )


# ---------------------------------------------------------------------------
# Provenance / no fabrication
# ---------------------------------------------------------------------------


def test_reports_versions_and_split(summary):
    assert summary["model_version"] == "risk-v1"
    assert summary["feature_schema_version"] == "features-v1"
    assert summary["decision_policy_version"] == "decision-v1"
    assert summary["split"] == "validation"


def test_never_uses_the_locked_test_split(summary):
    assert summary["split"] != "test"


def test_note_labels_prototype_assumptions_and_retrospective_figures(summary):
    assert "PROTOTYPE" in summary["note"]
    assert "retrospective" in summary["note"].lower()


def test_summary_contains_no_unsupported_metric_keys(summary):
    """Guards against reintroducing dashboard filler the dataset cannot
    support (SLAs, recovery-to-date, team throughput, win-rate trends)."""
    forbidden = {"sla", "trend", "recovery_to_date", "throughput", "avg_resolution_time", "win_rate_change"}
    assert not (forbidden & set(summary))


# ---------------------------------------------------------------------------
# Behavior under failure / isolation
# ---------------------------------------------------------------------------


def test_portfolio_view_uses_production_policy_not_playground_scenarios(client, summary, risk_model):
    """A wild playground scenario must not change the portfolio view."""
    client.post("/policy/simulate", json={"contest_cost": 50000, "high_confidence_probability": 0.99})
    after = client.get("/portfolio/summary").json()
    assert after["decisions"] == summary["decisions"]


def test_portfolio_view_does_not_touch_the_database(client, db_session, summary):
    from app.models import Dispute, Evidence

    before = (db_session.query(Dispute).count(), db_session.query(Evidence).count())
    assert client.get("/portfolio/summary").status_code == 200
    db_session.expire_all()
    assert (db_session.query(Dispute).count(), db_session.query(Evidence).count()) == before


def test_missing_dataset_reports_unavailable_rather_than_fabricating(client, monkeypatch, risk_model):
    """If the split CSVs are absent the endpoint must fail loudly, not
    invent an empty-but-plausible portfolio."""
    from app.api import portfolio as portfolio_api

    def _raise(*args, **kwargs):
        raise FileNotFoundError("missing disputes.csv")

    monkeypatch.setattr(portfolio_api, "get_scored_portfolio", _raise)
    resp = client.get("/portfolio/summary")
    assert resp.status_code == 503
    assert "not available" in resp.json()["detail"]
