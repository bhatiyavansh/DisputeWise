"""Target-leakage guards for the Phase 2 feature pipeline.

The model's credibility rests on the claim that no future or outcome
information reaches the features. These tests enforce that claim mechanically
rather than by convention.
"""

import inspect

import numpy as np
import pandas as pd
import pytest

from app.ml import features as features_module
from app.ml import schema
from app.ml.features import build_features, extract_target

pytest.importorskip("lightgbm")


# ---------------------------------------------------------------------------
# Structural guarantees
# ---------------------------------------------------------------------------


def test_build_features_cannot_accept_outcomes():
    """The strongest guarantee: the label table is not a parameter at all."""
    parameters = set(inspect.signature(build_features).parameters)
    assert parameters == {"disputes", "transactions", "customers", "evidence"}
    assert "outcomes" not in parameters


def test_outcome_columns_are_declared_forbidden():
    for column in ("favorable_outcome", "recovery_amount", "outcome_at", "outcome_source"):
        assert column in schema.FORBIDDEN_COLUMNS, f"{column} must be declared forbidden"


def test_generator_label_and_identifiers_are_forbidden():
    for column in (
        "scenario_archetype",
        "split",
        "dispute_id",
        "customer_id",
        "transaction_id",
        "merchant_id",
    ):
        assert column in schema.FORBIDDEN_COLUMNS


def test_protected_attribute_is_excluded():
    """Country is a national-origin proxy and must not be a feature."""
    assert "country" in schema.FORBIDDEN_COLUMNS
    assert "country" not in features_module.feature_names()


def test_allowlist_excludes_every_forbidden_column():
    """The only forbidden columns the builder may READ are declared derived-only.

    Join keys and raw identifiers used solely to compute a comparison (e.g.
    billing vs. shipping address) are read but must not survive as features;
    that they don't is asserted by
    test_no_forbidden_column_in_feature_matrix.
    """
    allowlisted = set().union(*schema.ALLOWED_SOURCE_COLUMNS.values())
    leaked = (allowlisted & set(schema.FORBIDDEN_COLUMNS)) - schema.DERIVED_ONLY_COLUMNS
    assert not leaked, f"allowlist admits forbidden columns: {sorted(leaked)}"


def test_derived_only_columns_never_become_features():
    from app.ml.features import feature_names

    assert not set(feature_names()) & schema.DERIVED_ONLY_COLUMNS


def test_no_outcome_column_is_allowlisted():
    """Outcome columns must not be readable from any table."""
    allowlisted = set().union(*schema.ALLOWED_SOURCE_COLUMNS.values())
    for column in ("favorable_outcome", "recovery_amount", "outcome_at", "outcome_source"):
        assert column not in allowlisted


# ---------------------------------------------------------------------------
# Behavioural guarantees against real data
# ---------------------------------------------------------------------------


def test_no_forbidden_column_in_feature_matrix(train_features):
    present = set(train_features.columns) & set(schema.FORBIDDEN_COLUMNS)
    assert not present, f"forbidden columns leaked into features: {sorted(present)}"


def test_no_target_leakage(train_features, train_target):
    """No single feature may near-perfectly reproduce the target.

    Real signal is expected (evidence genuinely drives outcomes); a
    correlation at |r| >= 0.95 would indicate the label itself leaked in.
    """
    target = train_target.to_numpy().astype(float)
    offenders = []
    for column in train_features.columns:
        series = train_features[column]
        valid = series.notna().to_numpy()
        if series.nunique(dropna=True) <= 1 or valid.sum() < 100:
            continue
        correlation = np.corrcoef(series.to_numpy(dtype=float)[valid], target[valid])[0, 1]
        if np.isfinite(correlation) and abs(correlation) >= 0.95:
            offenders.append((column, round(float(correlation), 4)))
    assert not offenders, f"features almost perfectly predict the target: {offenders}"


def test_injecting_outcome_columns_into_inputs_does_not_leak(train_split):
    """Even if a caller passes contaminated frames, no outcome column survives.

    Simulates a future refactor accidentally joining outcomes upstream.
    """
    disputes = train_split.disputes.head(500).copy()
    outcomes = train_split.outcomes.set_index("dispute_id")
    disputes["favorable_outcome"] = disputes["dispute_id"].map(outcomes["favorable_outcome"])
    disputes["recovery_amount"] = disputes["dispute_id"].map(outcomes["recovery_amount"])

    built = build_features(
        disputes, train_split.transactions, train_split.customers, train_split.evidence
    )
    assert "favorable_outcome" not in built.columns
    assert "recovery_amount" not in built.columns
    assert not set(built.columns) & set(schema.FORBIDDEN_COLUMNS)


def test_extract_target_is_the_only_path_to_labels(train_split):
    features = build_features(
        train_split.disputes.head(200),
        train_split.transactions,
        train_split.customers,
        train_split.evidence,
    )
    target = extract_target(train_split.outcomes, features.index)
    assert set(target.unique()) <= {0, 1}
    assert len(target) == len(features)
