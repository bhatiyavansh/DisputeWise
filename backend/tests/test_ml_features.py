"""Feature-engineering contract tests: determinism, schema stability, and
graceful handling of missing evidence / unknown categories.
"""

import numpy as np
import pandas as pd
import pytest

from app.ml import schema
from app.ml.features import build_features, categorical_feature_names, feature_names

pytest.importorskip("lightgbm")


# ---------------------------------------------------------------------------
# Schema stability
# ---------------------------------------------------------------------------


def test_feature_schema_stable():
    """Feature ordering must be deterministic and free of duplicates."""
    first = feature_names()
    second = feature_names()
    assert first == second
    assert len(first) == len(set(first)), "duplicate feature names"
    assert first[: len(schema.CATEGORICAL_FEATURES)] == list(schema.CATEGORICAL_FEATURES)


def test_every_evidence_type_has_features():
    names = set(feature_names())
    for evidence_type in schema.ALL_EVIDENCE_TYPES:
        for suffix in ("available", "strength", "value"):
            assert f"ev_{evidence_type}_{suffix}" in names


def test_built_columns_match_declared_schema(train_features):
    assert list(train_features.columns) == feature_names()


def test_feature_matrix_is_numeric(train_features):
    assert all(dtype.kind in "ifb" for dtype in train_features.dtypes)


def test_index_is_dispute_id(train_features, train_split):
    assert train_features.index.name == "dispute_id"
    assert set(train_features.index) == set(train_split.disputes["dispute_id"])


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_feature_generation_deterministic(train_split):
    subset = train_split.disputes.head(1000)
    first = build_features(subset, train_split.transactions, train_split.customers, train_split.evidence)
    second = build_features(subset, train_split.transactions, train_split.customers, train_split.evidence)
    pd.testing.assert_frame_equal(first, second)


def test_feature_generation_independent_of_input_row_order(train_split):
    subset = train_split.disputes.head(500)
    shuffled_evidence = train_split.evidence.sample(frac=1.0, random_state=0)
    baseline = build_features(subset, train_split.transactions, train_split.customers, train_split.evidence)
    reordered = build_features(subset, train_split.transactions, train_split.customers, shuffled_evidence)
    pd.testing.assert_frame_equal(baseline, reordered.loc[baseline.index])


def test_single_row_matches_batch(train_split):
    """A case scored alone must featurize identically to the same case in a batch.

    This is what makes the API's per-case path equivalent to offline scoring.
    """
    subset = train_split.disputes.head(50)
    batch = build_features(subset, train_split.transactions, train_split.customers, train_split.evidence)

    target_id = subset.iloc[10]["dispute_id"]
    single = build_features(
        subset[subset["dispute_id"] == target_id],
        train_split.transactions,
        train_split.customers,
        train_split.evidence[train_split.evidence["dispute_id"] == target_id],
    )
    pd.testing.assert_series_equal(
        batch.loc[target_id], single.loc[target_id], check_names=False
    )


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_missing_evidence_handled(train_split):
    """A case with no evidence rows still produces a full-width feature row."""
    subset = train_split.disputes.head(5)
    empty_evidence = train_split.evidence.iloc[0:0]

    built = build_features(subset, train_split.transactions, train_split.customers, empty_evidence)

    assert list(built.columns) == feature_names()
    assert len(built) == len(subset)
    # availability collapses to zero rather than becoming NaN or vanishing
    assert (built["evidence_available_count"] == 0).all()
    assert (built["evidence_completeness_ratio"] == 0).all()
    for evidence_type in schema.ALL_EVIDENCE_TYPES:
        assert (built[f"ev_{evidence_type}_available"] == 0).all()


def test_partial_evidence_handled(train_split):
    """Dropping one evidence type keeps the schema width and marks it absent."""
    subset = train_split.disputes.head(20)
    ids = set(subset["dispute_id"])
    evidence = train_split.evidence[
        train_split.evidence["dispute_id"].isin(ids) & (train_split.evidence["evidence_type"] != "cvv")
    ]

    built = build_features(subset, train_split.transactions, train_split.customers, evidence)

    assert list(built.columns) == feature_names()
    assert (built["ev_cvv_available"] == 0).all()
    assert built["ev_cvv_value"].isna().all()


def test_unknown_category_handled(train_split):
    """An unseen categorical value maps to the UNKNOWN sentinel, never crashes."""
    subset = train_split.disputes.head(20).copy()
    subset["reason_code"] = "some_future_reason_code_we_have_never_seen"

    transactions = train_split.transactions.copy()
    mask = transactions["transaction_id"].isin(subset["transaction_id"])
    transactions.loc[mask, "payment_method"] = "crypto_wallet"

    built = build_features(subset, transactions, train_split.customers, train_split.evidence)

    assert (built["reason_code"] == schema.UNKNOWN_CATEGORY_CODE).all()
    assert (built["payment_method"] == schema.UNKNOWN_CATEGORY_CODE).all()


def test_missing_required_column_raises(train_split):
    broken = train_split.disputes.drop(columns=["reason_code"])
    with pytest.raises(ValueError, match="missing required columns"):
        build_features(broken, train_split.transactions, train_split.customers, train_split.evidence)


def test_duplicate_disputes_rejected(train_split):
    duplicated = pd.concat([train_split.disputes.head(3), train_split.disputes.head(3)])
    with pytest.raises(ValueError, match="duplicate dispute_id"):
        build_features(
            duplicated, train_split.transactions, train_split.customers, train_split.evidence
        )


def test_extra_input_columns_are_ignored(train_split):
    """A stray column in an input frame must not become a feature."""
    disputes = train_split.disputes.head(100).copy()
    disputes["some_new_upstream_column"] = 1.23

    built = build_features(
        disputes, train_split.transactions, train_split.customers, train_split.evidence
    )
    assert "some_new_upstream_column" not in built.columns
    assert list(built.columns) == feature_names()


# ---------------------------------------------------------------------------
# Semantics
# ---------------------------------------------------------------------------


def test_completeness_ratio_bounds(train_features):
    ratio = train_features["evidence_completeness_ratio"]
    assert ratio.min() >= 0.0 and ratio.max() <= 1.0


def test_categorical_codes_within_vocabulary(train_features):
    for name in categorical_feature_names():
        codes = train_features[name]
        vocabulary_size = len(schema.CATEGORICAL_FEATURES[name])
        assert codes.min() >= schema.UNKNOWN_CATEGORY_CODE
        assert codes.max() < vocabulary_size


def test_unavailable_evidence_has_nan_value(train_features):
    """Absent evidence is NaN (LightGBM 'missing'), not a misleading zero."""
    for evidence_type in ("proof_of_delivery", "tracking_available"):
        unavailable = train_features[f"ev_{evidence_type}_available"] == 0
        if unavailable.any():
            assert train_features.loc[unavailable, f"ev_{evidence_type}_value"].isna().all()
