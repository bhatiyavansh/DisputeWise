"""Deterministic feature engineering for the Phase 2 winnability model.

    case + transaction + customer + evidence  ->  numeric feature matrix

LEAKAGE POLICY (structural)
---------------------------
`build_features()` deliberately does NOT accept the `outcomes` table. The
target (`favorable_outcome`) and its perfect proxy (`recovery_amount`) are
therefore physically unreachable from this module -- leakage is prevented by
the function signature, not by remembering to drop columns.

Customer-history features come exclusively from the `customers` table's
`previous_*` columns, which are as-of-account-state attributes recorded
before the dispute. We deliberately do NOT derive customer aggregates by
counting that customer's other rows in the dataset, because a customer's
other disputes may occur AFTER the dispute being scored (temporal leakage),
and aggregating their outcomes would touch the target directly. See
docs/phase2.md for the full rationale.

Determinism: no sampling, no hashing of unordered structures, and a fixed
column order (`feature_names()`), so the same input always yields a
byte-identical feature matrix.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from app.ml import schema

_EPS = 1e-9


# ---------------------------------------------------------------------------
# Column ordering
# ---------------------------------------------------------------------------

_CASE_FEATURES = [
    "dispute_amount",
    "dispute_amount_log",
    "transaction_amount",
    "transaction_amount_log",
    "transaction_capture_lag_minutes",
    "days_transaction_to_dispute",
    "days_dispute_to_deadline",
]

_AUTH_FEATURES = [
    "three_ds_authenticated",
    "avs_match",
    "cvv_match",
    "billing_shipping_match",
]

_CUSTOMER_FEATURES = [
    "customer_account_age_days",
    "customer_previous_order_count",
    "customer_previous_successful_order_count",
    "customer_previous_dispute_count",
    "customer_previous_refund_count",
    "customer_success_ratio",
    "customer_dispute_ratio",
    "customer_refund_ratio",
]

_COMPLETENESS_FEATURES = [
    "evidence_available_count",
    "evidence_completeness_ratio",
    "strong_evidence_count",
    "evidence_strength_mean",
    "high_relevance_total_count",
    "high_relevance_available_count",
    "high_relevance_completeness_ratio",
    "high_relevance_strength_mean",
    "authentication_evidence_available_count",
    "authentication_evidence_strength_mean",
    "authentication_evidence_present",
    "fulfillment_evidence_available_count",
    "fulfillment_evidence_strength_mean",
    "fulfillment_evidence_present",
    "customer_evidence_available_count",
    "customer_evidence_strength_mean",
    "customer_evidence_present",
    "communication_evidence_available_count",
    "communication_evidence_strength_mean",
    "communication_evidence_present",
]

_FULFILLMENT_DERIVED = ["delivery_before_dispute", "delivery_lag_days"]


def _evidence_feature_names() -> list[str]:
    names: list[str] = []
    for evidence_type in schema.ALL_EVIDENCE_TYPES:
        names.append(f"ev_{evidence_type}_available")
        names.append(f"ev_{evidence_type}_strength")
        names.append(f"ev_{evidence_type}_value")
    return names


def feature_names() -> list[str]:
    """Canonical, stable feature ordering. Persisted with the model."""
    return (
        list(schema.CATEGORICAL_FEATURES.keys())
        + _CASE_FEATURES
        + _AUTH_FEATURES
        + _CUSTOMER_FEATURES
        + _FULFILLMENT_DERIVED
        + _evidence_feature_names()
        + _COMPLETENESS_FEATURES
    )


def categorical_feature_names() -> list[str]:
    return list(schema.CATEGORICAL_FEATURES.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce", format="mixed")


def _to_bool_float(series: pd.Series) -> pd.Series:
    """Normalize the several boolean encodings CSV/Postgres/ORM can produce."""
    if series.dtype == bool:
        return series.astype(float)
    mapping = {
        True: 1.0,
        False: 0.0,
        "True": 1.0,
        "False": 0.0,
        "true": 1.0,
        "false": 0.0,
        "t": 1.0,
        "f": 0.0,
        1: 1.0,
        0: 0.0,
    }
    return series.map(mapping).astype(float)


def _encode_categorical(series: pd.Series, vocabulary: tuple[str, ...]) -> pd.Series:
    """Stable integer encoding; unseen/missing values map to UNKNOWN_CATEGORY_CODE."""
    lookup = {value: index for index, value in enumerate(vocabulary)}
    return series.map(lookup).fillna(schema.UNKNOWN_CATEGORY_CODE).astype(int)


def _parse_evidence_values(evidence: pd.DataFrame) -> pd.Series:
    """Turn each evidence row's JSON `value` into a single numeric signal.

    Returns a float Series aligned to `evidence`'s index. Unavailable rows and
    unparseable payloads become NaN, which LightGBM handles natively as
    "missing" -- semantically the correct representation for absent evidence.
    """
    out = pd.Series(np.nan, index=evidence.index, dtype=float)

    available_mask = _to_bool_float(evidence["available"]).fillna(0.0) > 0.5
    if not available_mask.any():
        return out

    for evidence_type, (json_key, kind) in schema.EVIDENCE_VALUE_SPEC.items():
        type_mask = available_mask & (evidence["evidence_type"] == evidence_type)
        if not type_mask.any():
            continue

        raw_values = evidence.loc[type_mask, "value"]

        def extract(payload: object) -> float:
            if payload is None or (isinstance(payload, float) and np.isnan(payload)):
                return np.nan
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except (ValueError, TypeError):
                    return np.nan
            if not isinstance(payload, dict) or json_key not in payload:
                return np.nan
            item = payload[json_key]
            if item is None:
                return np.nan
            if kind == "bool":
                return float(bool(item))
            if kind == "count":
                try:
                    return float(item)
                except (TypeError, ValueError):
                    return np.nan
            if kind.startswith("equals:"):
                return float(str(item) == kind.split(":", 1)[1])
            if kind == "timestamp":
                parsed = pd.to_datetime(item, utc=True, errors="coerce")
                return float(parsed.value) if parsed is not pd.NaT and not pd.isna(parsed) else np.nan
            return np.nan

        out.loc[type_mask] = raw_values.map(extract).astype(float)

    return out


def _pivot_evidence(evidence: pd.DataFrame, dispute_ids: pd.Index) -> dict[str, pd.DataFrame]:
    """Pivot the long evidence table into dispute x evidence_type matrices.

    Always returns every declared evidence type as a column, even if entirely
    absent from the input, so the feature matrix width is schema-determined
    rather than data-determined.
    """
    working = evidence.copy()
    working["_available"] = _to_bool_float(working["available"]).fillna(0.0)
    working["_strength"] = pd.to_numeric(working["strength"], errors="coerce").fillna(0.0)
    working["_value"] = _parse_evidence_values(working)
    working["_is_high_relevance"] = (working["relevance"].astype(str) == "high").astype(float)
    working["_high_relevance_available"] = working["_is_high_relevance"] * working["_available"]

    columns = list(schema.ALL_EVIDENCE_TYPES)
    frames: dict[str, pd.DataFrame] = {}
    for key, source_column, fill in [
        ("available", "_available", 0.0),
        ("strength", "_strength", 0.0),
        ("value", "_value", np.nan),
        ("is_high_relevance", "_is_high_relevance", 0.0),
        ("high_relevance_available", "_high_relevance_available", 0.0),
    ]:
        pivoted = working.pivot_table(
            index="dispute_id", columns="evidence_type", values=source_column, aggfunc="first"
        )
        pivoted = pivoted.reindex(index=dispute_ids, columns=columns)
        if fill is not np.nan:
            pivoted = pivoted.fillna(fill)
        frames[key] = pivoted

    return frames


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_features(
    disputes: pd.DataFrame,
    transactions: pd.DataFrame,
    customers: pd.DataFrame,
    evidence: pd.DataFrame,
) -> pd.DataFrame:
    """Build the model feature matrix, indexed by dispute_id.

    Note the absent `outcomes` parameter -- see the module docstring.
    """
    for name, frame, allowed in [
        ("disputes", disputes, schema.ALLOWED_SOURCE_COLUMNS["disputes"]),
        ("transactions", transactions, schema.ALLOWED_SOURCE_COLUMNS["transactions"]),
        ("customers", customers, schema.ALLOWED_SOURCE_COLUMNS["customers"]),
        ("evidence", evidence, schema.ALLOWED_SOURCE_COLUMNS["evidence"]),
    ]:
        missing = allowed - set(frame.columns)
        if missing:
            raise ValueError(f"{name} frame is missing required columns: {sorted(missing)}")

    # Read only allowlisted columns -- anything else in the input is ignored
    # outright, so a future extra column cannot silently become a feature.
    disputes = disputes[sorted(schema.ALLOWED_SOURCE_COLUMNS["disputes"])].copy()
    transactions = transactions[sorted(schema.ALLOWED_SOURCE_COLUMNS["transactions"])].copy()
    customers = customers[sorted(schema.ALLOWED_SOURCE_COLUMNS["customers"])].copy()
    evidence = evidence[sorted(schema.ALLOWED_SOURCE_COLUMNS["evidence"])].copy()

    base = disputes.merge(
        transactions, on="transaction_id", how="left", suffixes=("_dispute", "_transaction")
    ).merge(customers, on="customer_id", how="left", suffixes=("", "_customer"))

    if base["dispute_id"].duplicated().any():
        raise ValueError("duplicate dispute_id rows after join -- refusing to build ambiguous features")

    base = base.set_index("dispute_id")
    dispute_ids = base.index

    dispute_created = _to_datetime(base["created_at_dispute"])
    transaction_created = _to_datetime(base["created_at_transaction"])
    transaction_captured = _to_datetime(base["captured_at"])
    response_deadline = _to_datetime(base["response_deadline"])

    dispute_amount = pd.to_numeric(base["dispute_amount"], errors="coerce")
    transaction_amount = pd.to_numeric(base["amount"], errors="coerce")

    data: dict[str, pd.Series] = {}

    # --- categoricals -------------------------------------------------------
    source_for_categorical = {
        "reason_code": base["reason_code"],
        "payment_method": base["payment_method"],
        "transaction_status": base["status"],
        "avs_result": base["avs_result"],
        "cvv_result": base["cvv_result"],
    }
    for name, vocabulary in schema.CATEGORICAL_FEATURES.items():
        data[name] = _encode_categorical(source_for_categorical[name].astype("object"), vocabulary)

    # --- case / transaction -------------------------------------------------
    data["dispute_amount"] = dispute_amount
    data["dispute_amount_log"] = np.log1p(dispute_amount.clip(lower=0))
    data["transaction_amount"] = transaction_amount
    data["transaction_amount_log"] = np.log1p(transaction_amount.clip(lower=0))
    data["transaction_capture_lag_minutes"] = (
        transaction_captured - transaction_created
    ).dt.total_seconds() / 60.0
    data["days_transaction_to_dispute"] = (
        dispute_created - transaction_created
    ).dt.total_seconds() / 86400.0
    data["days_dispute_to_deadline"] = (
        response_deadline - dispute_created
    ).dt.total_seconds() / 86400.0

    # --- authentication -----------------------------------------------------
    data["three_ds_authenticated"] = _to_bool_float(base["three_ds_authenticated"])
    data["avs_match"] = (base["avs_result"].astype(str) == "Y").astype(float)
    data["cvv_match"] = (base["cvv_result"].astype(str) == "M").astype(float)
    data["billing_shipping_match"] = (
        base["billing_address_id"].astype(str) == base["shipping_address_id"].astype(str)
    ).astype(float)

    # --- customer history (as-of attributes; never dataset aggregates) ------
    previous_orders = pd.to_numeric(base["previous_order_count"], errors="coerce")
    previous_successful = pd.to_numeric(base["previous_successful_order_count"], errors="coerce")
    previous_disputes = pd.to_numeric(base["previous_dispute_count"], errors="coerce")
    previous_refunds = pd.to_numeric(base["previous_refund_count"], errors="coerce")
    order_denominator = previous_orders.clip(lower=1)

    data["customer_account_age_days"] = pd.to_numeric(base["account_age_days"], errors="coerce")
    data["customer_previous_order_count"] = previous_orders
    data["customer_previous_successful_order_count"] = previous_successful
    data["customer_previous_dispute_count"] = previous_disputes
    data["customer_previous_refund_count"] = previous_refunds
    data["customer_success_ratio"] = previous_successful / order_denominator
    data["customer_dispute_ratio"] = previous_disputes / order_denominator
    data["customer_refund_ratio"] = previous_refunds / order_denominator

    # --- evidence pivot -----------------------------------------------------
    pivots = _pivot_evidence(evidence, dispute_ids)
    available = pivots["available"]
    strength = pivots["strength"]
    value = pivots["value"]

    # delivery_timestamp's parsed value is epoch-nanoseconds; convert it into
    # lag/ordering features and keep the raw epoch out of the matrix.
    delivery_epoch = value["delivery_timestamp"]
    delivery_datetime = pd.to_datetime(delivery_epoch, unit="ns", utc=True, errors="coerce")
    data["delivery_before_dispute"] = np.where(
        delivery_datetime.isna(), np.nan, (delivery_datetime < dispute_created).astype(float)
    )
    data["delivery_lag_days"] = (delivery_datetime - transaction_created).dt.total_seconds() / 86400.0

    for evidence_type in schema.ALL_EVIDENCE_TYPES:
        data[f"ev_{evidence_type}_available"] = available[evidence_type]
        data[f"ev_{evidence_type}_strength"] = strength[evidence_type]
        column = value[evidence_type]
        if evidence_type == "delivery_timestamp":
            # already represented by the lag features above; keep the slot
            # numeric and non-degenerate without leaking an absolute date
            column = data["delivery_lag_days"]
        data[f"ev_{evidence_type}_value"] = column

    # --- completeness aggregates -------------------------------------------
    total_types = float(len(schema.ALL_EVIDENCE_TYPES))
    available_count = available.sum(axis=1)
    data["evidence_available_count"] = available_count
    data["evidence_completeness_ratio"] = available_count / total_types
    data["strong_evidence_count"] = (
        (strength >= schema.STRONG_EVIDENCE_STRENGTH_THRESHOLD).astype(float).sum(axis=1)
    )
    data["evidence_strength_mean"] = strength.mean(axis=1)

    high_relevance_total = pivots["is_high_relevance"].sum(axis=1)
    high_relevance_available = pivots["high_relevance_available"].sum(axis=1)
    data["high_relevance_total_count"] = high_relevance_total
    data["high_relevance_available_count"] = high_relevance_available
    data["high_relevance_completeness_ratio"] = high_relevance_available / high_relevance_total.clip(lower=1)
    high_relevance_strength = strength.where(pivots["is_high_relevance"] > 0.5)
    data["high_relevance_strength_mean"] = high_relevance_strength.mean(axis=1)

    for category, evidence_types in schema.EVIDENCE_CATEGORIES.items():
        types = list(evidence_types)
        category_available = available[types].sum(axis=1)
        data[f"{category}_evidence_available_count"] = category_available
        data[f"{category}_evidence_strength_mean"] = strength[types].mean(axis=1)
        data[f"{category}_evidence_present"] = (category_available > 0).astype(float)

    ordered = feature_names()
    frame = pd.DataFrame({name: data[name] for name in ordered}, index=dispute_ids, columns=ordered)

    # Guard: no forbidden column may have survived into the matrix.
    forbidden_present = set(frame.columns) & set(schema.FORBIDDEN_COLUMNS)
    if forbidden_present:
        raise RuntimeError(f"forbidden columns leaked into feature matrix: {sorted(forbidden_present)}")

    for name in categorical_feature_names():
        frame[name] = frame[name].astype(int)

    return frame


def extract_target(outcomes: pd.DataFrame, dispute_ids: pd.Index) -> pd.Series:
    """Extract the aligned binary target.

    Kept deliberately separate from `build_features` so the outcomes table is
    only ever touched at label-construction time, never during featurization.
    """
    target = outcomes.set_index("dispute_id")["favorable_outcome"]
    aligned = target.reindex(dispute_ids)
    if aligned.isna().any():
        raise ValueError("missing favorable_outcome for one or more disputes")
    return _to_bool_float(aligned).astype(int)
