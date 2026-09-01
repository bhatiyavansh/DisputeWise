"""Model, calibration, and SHAP tests."""

import numpy as np
import pandas as pd
import pytest

from app.ml import schema
from app.ml.baseline import baseline_scores, best_baseline
from app.ml.calibration import (
    Calibrator,
    brier_score,
    calibration_curve_points,
    expected_calibration_error,
    fit_calibrator,
)
from app.ml.explain import describe_feature, top_factors
from app.ml.features import categorical_feature_names, feature_names

pytest.importorskip("lightgbm")
pytest.importorskip("shap")


# ---------------------------------------------------------------------------
# Training path
# ---------------------------------------------------------------------------


def test_model_trains(train_features, train_target):
    """Train a small booster end-to-end to prove the training path works."""
    import lightgbm as lgb

    subset = train_features.head(3000)
    labels = train_target.head(3000)

    dataset = lgb.Dataset(subset, label=labels, categorical_feature=categorical_feature_names())
    booster = lgb.train(
        {
            "objective": "binary",
            "verbosity": -1,
            "seed": 42,
            "deterministic": True,
            "force_row_wise": True,
            "num_threads": 2,
            "num_leaves": 15,
            "min_data_in_leaf": 50,
        },
        dataset,
        num_boost_round=25,
    )

    assert booster.num_trees() == 25
    predictions = booster.predict(subset)
    assert len(predictions) == len(subset)
    assert np.all((predictions >= 0.0) & (predictions <= 1.0))


def test_trained_artifact_metadata(risk_model):
    assert risk_model.model_version == schema.MODEL_VERSION
    assert risk_model.feature_schema_version == schema.FEATURE_SCHEMA_VERSION
    assert risk_model.feature_names == feature_names()
    assert risk_model.calibration_method in {"sigmoid", "isotonic", "identity"}
    assert 0.0 < float(risk_model.config["operating_threshold"]) < 1.0


def test_model_config_records_split_usage(risk_model):
    """The artifact must state that the locked test set was not used to train."""
    usage = risk_model.config["split_usage"]
    assert "never used during training" in usage["locked_test"]


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


def test_model_predicts(risk_model, train_features):
    predictions = risk_model.predict_raw(train_features.head(200))
    assert len(predictions) == 200
    assert np.isfinite(predictions).all()


def test_probability_range(risk_model, train_features):
    raw = risk_model.predict_raw(train_features.head(500))
    assert raw.min() >= 0.0 and raw.max() <= 1.0


def test_calibrated_probability_range(risk_model, train_features):
    calibrated = risk_model.predict_calibrated(train_features.head(500))
    assert calibrated.min() >= 0.0 and calibrated.max() <= 1.0
    assert np.isfinite(calibrated).all()


def test_prediction_deterministic(risk_model, train_features):
    subset = train_features.head(300)
    first = risk_model.predict_calibrated(subset)
    second = risk_model.predict_calibrated(subset)
    np.testing.assert_array_equal(first, second)


def test_prediction_independent_of_column_order(risk_model, train_features):
    """Feature alignment must be by name, not by position."""
    subset = train_features.head(100)
    shuffled = subset[list(reversed(subset.columns))]
    np.testing.assert_allclose(
        risk_model.predict_raw(subset), risk_model.predict_raw(shuffled), rtol=0, atol=0
    )


def test_missing_feature_column_raises(risk_model, train_features):
    with pytest.raises(ValueError, match="missing columns"):
        risk_model.predict_raw(train_features.head(10).drop(columns=["reason_code"]))


def test_model_discriminates_better_than_baseline(risk_model, train_features, train_target):
    """Sanity check that the model beats the evidence-completeness heuristic."""
    from sklearn.metrics import roc_auc_score

    subset = train_features.head(5000)
    labels = train_target.head(5000).to_numpy()

    model_auc = roc_auc_score(labels, risk_model.predict_calibrated(subset))
    _, _, baseline_aucs = best_baseline(baseline_scores(subset), labels)
    assert model_auc > max(baseline_aucs.values())


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["sigmoid", "isotonic"])
def test_calibrator_fits(method):
    rng = np.random.default_rng(0)
    raw = rng.uniform(0.01, 0.99, 2000)
    y = (rng.uniform(size=2000) < raw).astype(int)

    calibrator = fit_calibrator(method, raw, y)
    calibrated = calibrator.predict(raw)

    assert calibrator.method == method
    assert len(calibrated) == len(raw)
    assert calibrated.min() >= 0.0 and calibrated.max() <= 1.0


@pytest.mark.parametrize("method", ["sigmoid", "isotonic", "identity"])
def test_calibrator_json_roundtrip(method):
    rng = np.random.default_rng(1)
    raw = rng.uniform(0.01, 0.99, 500)
    y = (rng.uniform(size=500) < raw).astype(int)

    original = fit_calibrator(method, raw, y)
    restored = Calibrator.from_dict(original.to_dict())
    np.testing.assert_allclose(original.predict(raw), restored.predict(raw))


def test_calibration_improves_a_miscalibrated_score():
    """A deliberately skewed score should get closer to truth after calibration."""
    rng = np.random.default_rng(2)
    true_probability = rng.uniform(0.05, 0.95, 4000)
    y = (rng.uniform(size=4000) < true_probability).astype(int)
    skewed = np.clip(true_probability**2, 1e-3, 1 - 1e-3)  # systematically under-confident

    calibrator = fit_calibrator("isotonic", skewed, y)
    assert brier_score(y, calibrator.predict(skewed)) < brier_score(y, skewed)


def test_ece_and_curve_are_well_formed():
    rng = np.random.default_rng(3)
    probability = rng.uniform(size=1000)
    y = (rng.uniform(size=1000) < probability).astype(int)

    ece = expected_calibration_error(y, probability)
    assert 0.0 <= ece <= 1.0

    points = calibration_curve_points(y, probability, n_bins=10)
    assert sum(point["count"] for point in points) == 1000
    for point in points:
        assert 0.0 <= point["mean_predicted"] <= 1.0
        assert 0.0 <= point["observed_frequency"] <= 1.0


def test_unknown_calibration_method_rejected():
    with pytest.raises(ValueError, match="unknown calibration method"):
        fit_calibrator("magic", np.array([0.5]), np.array([1]))


# ---------------------------------------------------------------------------
# SHAP
# ---------------------------------------------------------------------------


def test_shap_explanation_generated(risk_model, train_features):
    subset = train_features.head(20)
    contributions = risk_model.explain(subset)
    assert contributions.shape == (len(subset), len(risk_model.feature_names))
    assert np.isfinite(contributions).all()


def test_shap_matches_lightgbm_native_contributions(risk_model, train_features):
    """Cross-check shap.TreeExplainer against LightGBM's own TreeSHAP."""
    subset = train_features.head(25)
    shap_values = risk_model.explain(subset)
    native = risk_model._booster.predict(subset, pred_contrib=True)[:, :-1]
    np.testing.assert_allclose(shap_values, native, rtol=1e-5, atol=1e-6)


def test_shap_is_deterministic(risk_model, train_features):
    subset = train_features.head(15)
    np.testing.assert_array_equal(risk_model.explain(subset), risk_model.explain(subset))


def test_explanation_features_exist(risk_model, train_features):
    scores = risk_model.score_cases(train_features.head(10))
    valid = set(risk_model.feature_names)
    for score in scores:
        for factor in score.top_positive_factors + score.top_negative_factors:
            assert factor["feature"] in valid
            assert isinstance(factor["description"], str) and factor["description"]


def test_factor_signs_are_correct(risk_model, train_features):
    for score in risk_model.score_cases(train_features.head(10)):
        assert all(f["contribution"] > 0 for f in score.top_positive_factors)
        assert all(f["contribution"] < 0 for f in score.top_negative_factors)


def test_factors_sorted_by_magnitude(risk_model, train_features):
    for score in risk_model.score_cases(train_features.head(10)):
        positives = [f["contribution"] for f in score.top_positive_factors]
        negatives = [f["contribution"] for f in score.top_negative_factors]
        assert positives == sorted(positives, reverse=True)
        assert negatives == sorted(negatives)


def test_score_cases_matches_predict(risk_model, train_features):
    subset = train_features.head(10)
    scores = risk_model.score_cases(subset)
    expected = risk_model.predict_calibrated(subset)
    np.testing.assert_allclose([s.calibrated_probability for s in scores], expected)


def test_top_factors_respects_top_n(risk_model, train_features):
    scores = risk_model.score_cases(train_features.head(3), top_n=3)
    for score in scores:
        assert len(score.top_positive_factors) <= 3
        assert len(score.top_negative_factors) <= 3


# ---------------------------------------------------------------------------
# Human-readable explanations
# ---------------------------------------------------------------------------


def test_descriptions_reflect_actual_state():
    """Phrasing must follow the value, not just the feature name."""
    assert "was authenticated with 3-D Secure" in describe_feature("three_ds_authenticated", 1.0)
    assert "was not authenticated with 3-D Secure" in describe_feature("three_ds_authenticated", 0.0)
    assert "was successfully completed" in describe_feature("ev_three_ds_value", 1.0)
    assert "was not completed" in describe_feature("ev_three_ds_value", 0.0)
    assert "is available" in describe_feature("ev_delivery_confirmed_available", 1.0)
    assert "No delivery confirmation evidence" in describe_feature("ev_delivery_confirmed_available", 0.0)


def test_missing_evidence_described_as_missing():
    assert "No proof of delivery evidence" in describe_feature("ev_proof_of_delivery_value", float("nan"))


def test_every_feature_has_a_description():
    for name in feature_names():
        description = describe_feature(name, 1.0)
        assert isinstance(description, str) and description.strip()


def test_categorical_descriptions_use_vocabulary():
    assert "unauthorized" in describe_feature("reason_code", 0).lower()
    assert "goods or services not received" in describe_feature("reason_code", 1).lower()
    assert "duplicate" in describe_feature("reason_code", 2).lower()


def test_unknown_category_described_gracefully():
    assert "unrecognized" in describe_feature("reason_code", schema.UNKNOWN_CATEGORY_CODE).lower()


def test_risk_bands():
    assert schema.risk_band(0.95) == schema.RISK_BAND_HIGH
    assert schema.risk_band(0.55) == schema.RISK_BAND_MEDIUM
    assert schema.risk_band(0.10) == schema.RISK_BAND_LOW
    assert schema.risk_band(schema.RISK_BAND_HIGH_THRESHOLD) == schema.RISK_BAND_HIGH
    assert schema.risk_band(schema.RISK_BAND_LOW_THRESHOLD) == schema.RISK_BAND_MEDIUM
