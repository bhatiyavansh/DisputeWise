"""SHAP explanations and human-readable evidence language.

Two responsibilities:

1. `shap_contributions()` -- exact TreeSHAP attributions from the trained
   LightGBM model. These are real model attributions; nothing here invents,
   smooths, or post-hoc rationalizes a contribution.

2. `describe_feature()` -- turns a (feature, actual value) pair into merchant-
   readable evidence language. The phrasing is selected by the case's ACTUAL
   feature state, so a description can never contradict the data. No LLM is
   involved in this phase.

Units: SHAP contributions are in the model's raw margin (log-odds) space, not
probability space. A contribution of +0.5 means "this feature pushed the
log-odds of a favorable outcome up by 0.5", which is monotone in probability
but not itself a probability delta. Callers should present them as relative
drivers, not as additive percentage points.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.ml import schema

# ---------------------------------------------------------------------------
# Human-readable labels
# ---------------------------------------------------------------------------

EVIDENCE_LABELS: dict[str, str] = {
    "three_ds": "3-D Secure authentication",
    "avs": "address verification (AVS)",
    "cvv": "card security code (CVV) verification",
    "device_match": "device fingerprint match",
    "ip_match": "IP address match",
    "delivery_confirmed": "delivery confirmation",
    "tracking_available": "carrier tracking",
    "delivery_address_match": "delivery address match",
    "delivery_timestamp": "delivery timestamp",
    "proof_of_delivery": "proof of delivery",
    "prior_order_history": "prior order history",
    "prior_successful_orders": "prior successful orders",
    "prior_disputes": "prior dispute history",
    "customer_communication_available": "customer communication records",
    "cancellation_request": "cancellation request record",
    "refund_request": "refund request record",
}

# Phrasing for a present-and-positive vs present-and-negative evidence value.
_EVIDENCE_VALUE_PHRASES: dict[str, tuple[str, str]] = {
    "three_ds": ("3-D Secure authentication was successfully completed.", "3-D Secure authentication was not completed."),
    "avs": ("The billing address passed AVS verification.", "The billing address did not pass AVS verification."),
    "cvv": ("The card security code (CVV) matched.", "The card security code (CVV) did not match."),
    "device_match": ("The transaction came from a device previously associated with this customer.", "The transaction came from an unrecognized device."),
    "ip_match": ("The transaction IP address matched the customer's usual location.", "The transaction IP address did not match the customer's usual location."),
    "delivery_confirmed": ("Delivery of the order was confirmed.", "Delivery of the order was not confirmed."),
    "tracking_available": ("Carrier tracking information is available.", "No carrier tracking information is available."),
    "delivery_address_match": ("The delivery address matched the address on the order.", "The delivery address did not match the address on the order."),
    "proof_of_delivery": ("Proof of delivery is on file.", "No proof of delivery is on file."),
    "customer_communication_available": ("Customer communication records are available for this order.", "No customer communication records were found."),
    "cancellation_request": ("The customer submitted a cancellation request.", "No cancellation request was submitted by the customer."),
    "refund_request": ("The customer submitted a refund request.", "No refund request was submitted by the customer."),
}

# Non-evidence features: (description when high/true, description when low/false).
_SCALAR_FEATURE_PHRASES: dict[str, tuple[str, str]] = {
    "three_ds_authenticated": ("The transaction was authenticated with 3-D Secure.", "The transaction was not authenticated with 3-D Secure."),
    "avs_match": ("The billing address passed AVS verification.", "The billing address did not pass AVS verification."),
    "cvv_match": ("The card security code (CVV) matched.", "The card security code (CVV) did not match."),
    "billing_shipping_match": ("The billing and shipping addresses match.", "The billing and shipping addresses differ."),
    "delivery_before_dispute": ("The order was delivered before the dispute was filed.", "The order was not delivered before the dispute was filed."),
    "authentication_evidence_present": ("Authentication evidence is available.", "No authentication evidence is available."),
    "fulfillment_evidence_present": ("Fulfillment evidence is available.", "No fulfillment evidence is available."),
    "customer_evidence_present": ("Customer history evidence is available.", "No customer history evidence is available."),
    "communication_evidence_present": ("Customer communication evidence is available.", "No customer communication evidence is available."),
}

# Features described by magnitude rather than a binary state.
_MAGNITUDE_FEATURE_TEMPLATES: dict[str, str] = {
    "dispute_amount": "The disputed amount is {value:,.2f}.",
    "transaction_amount": "The transaction amount is {value:,.2f}.",
    "dispute_amount_log": "The disputed amount is {raw:,.2f}.",
    "transaction_amount_log": "The transaction amount is {raw:,.2f}.",
    "days_transaction_to_dispute": "The dispute was filed {value:.0f} days after the transaction.",
    "days_dispute_to_deadline": "There are {value:.0f} days between the dispute and the response deadline.",
    "transaction_capture_lag_minutes": "The payment was captured {value:.0f} minutes after authorization.",
    "delivery_lag_days": "Delivery occurred {value:.0f} days after the transaction.",
    "customer_account_age_days": "The customer account is {value:.0f} days old.",
    "customer_previous_order_count": "The customer has {value:.0f} previous orders.",
    "customer_previous_successful_order_count": "The customer has {value:.0f} previous successful orders.",
    "customer_previous_dispute_count": "The customer has {value:.0f} previous disputes.",
    "customer_previous_refund_count": "The customer has {value:.0f} previous refunds.",
    "customer_success_ratio": "{value:.0%} of the customer's previous orders completed successfully.",
    "customer_dispute_ratio": "The customer disputes {value:.0%} of their orders.",
    "customer_refund_ratio": "The customer has requested refunds on {value:.0%} of their orders.",
    "evidence_available_count": "{value:.0f} of 16 evidence items are available.",
    "evidence_completeness_ratio": "Overall evidence completeness is {value:.0%}.",
    "strong_evidence_count": "{value:.0f} evidence items are strong.",
    "evidence_strength_mean": "Average evidence strength is {value:.2f}.",
    "high_relevance_total_count": "{value:.0f} evidence types are highly relevant to this reason code.",
    "high_relevance_available_count": "{value:.0f} highly relevant evidence items are available.",
    "high_relevance_completeness_ratio": "{value:.0%} of the evidence that matters most for this reason code is available.",
    "high_relevance_strength_mean": "Average strength of highly relevant evidence is {value:.2f}.",
    "authentication_evidence_available_count": "{value:.0f} authentication evidence items are available.",
    "authentication_evidence_strength_mean": "Average authentication evidence strength is {value:.2f}.",
    "fulfillment_evidence_available_count": "{value:.0f} fulfillment evidence items are available.",
    "fulfillment_evidence_strength_mean": "Average fulfillment evidence strength is {value:.2f}.",
    "customer_evidence_available_count": "{value:.0f} customer history evidence items are available.",
    "customer_evidence_strength_mean": "Average customer history evidence strength is {value:.2f}.",
    "communication_evidence_available_count": "{value:.0f} communication evidence items are available.",
    "communication_evidence_strength_mean": "Average communication evidence strength is {value:.2f}.",
}

_CATEGORICAL_LABELS: dict[str, dict[str, str]] = {
    "reason_code": {
        "unauthorized_transaction": "The dispute reason is an unauthorized/fraudulent transaction claim.",
        "goods_not_received": "The dispute reason is goods or services not received.",
        "duplicate_charge": "The dispute reason is a duplicate charge claim.",
    },
    "payment_method": {
        "card": "The payment was made by card.",
        "upi": "The payment was made via UPI.",
        "netbanking": "The payment was made via net banking.",
    },
    "transaction_status": {
        "captured": "The payment was captured.",
        "refunded": "The payment was refunded.",
        "failed": "The payment failed.",
    },
    "avs_result": {
        "Y": "AVS returned a full match.",
        "N": "AVS returned no match.",
        "U": "AVS result was unavailable.",
        "M": "AVS returned a partial match.",
    },
    "cvv_result": {
        "M": "The CVV matched.",
        "N": "The CVV did not match.",
        "U": "The CVV result was unavailable.",
    },
}


def describe_feature(name: str, value: Any) -> str:
    """Render one (feature, actual value) pair as merchant-readable text.

    The phrasing is chosen from the value, so descriptions always reflect the
    real state of the case rather than a generic feature blurb.
    """
    is_missing = value is None or (isinstance(value, float) and np.isnan(value))

    # --- categoricals -------------------------------------------------------
    if name in schema.CATEGORICAL_FEATURES:
        vocabulary = schema.CATEGORICAL_FEATURES[name]
        if is_missing:
            return f"The {name.replace('_', ' ')} is unknown."
        code = int(value)
        if code < 0 or code >= len(vocabulary):
            return f"The {name.replace('_', ' ')} is an unrecognized value."
        category = vocabulary[code]
        return _CATEGORICAL_LABELS.get(name, {}).get(category, f"The {name.replace('_', ' ')} is {category}.")

    # --- per-evidence-type features ----------------------------------------
    if name.startswith("ev_"):
        for evidence_type in schema.ALL_EVIDENCE_TYPES:
            for suffix in ("_available", "_strength", "_value"):
                if name == f"ev_{evidence_type}{suffix}":
                    label = EVIDENCE_LABELS[evidence_type]
                    if suffix == "_available":
                        if is_missing:
                            return f"Availability of {label} is unknown."
                        return (
                            f"{label.capitalize()} evidence is available."
                            if float(value) > 0.5
                            else f"No {label} evidence is on file."
                        )
                    if suffix == "_strength":
                        if is_missing:
                            return f"Strength of {label} evidence is unknown."
                        return f"{label.capitalize()} evidence has a strength of {float(value):.2f}."
                    # suffix == "_value"
                    if is_missing:
                        return f"No {label} evidence is on file."
                    if evidence_type in schema.NON_BINARY_EVIDENCE_VALUES:
                        if evidence_type == "delivery_timestamp":
                            return f"Delivery occurred {float(value):.0f} days after the transaction."
                        return f"{label.capitalize()} shows a count of {float(value):.0f}."
                    positive, negative = _EVIDENCE_VALUE_PHRASES[evidence_type]
                    return positive if float(value) > 0.5 else negative

    # --- binary scalar features --------------------------------------------
    if name in _SCALAR_FEATURE_PHRASES:
        positive, negative = _SCALAR_FEATURE_PHRASES[name]
        if is_missing:
            return negative
        return positive if float(value) > 0.5 else negative

    # --- magnitude features -------------------------------------------------
    if name in _MAGNITUDE_FEATURE_TEMPLATES:
        if is_missing:
            return f"{name.replace('_', ' ').capitalize()} is unavailable."
        template = _MAGNITUDE_FEATURE_TEMPLATES[name]
        numeric = float(value)
        return template.format(value=numeric, raw=float(np.expm1(numeric)) if "log" in name else numeric)

    return f"{name.replace('_', ' ').capitalize()}: {value}"


# ---------------------------------------------------------------------------
# SHAP
# ---------------------------------------------------------------------------


class ShapExplainer:
    """Thin wrapper over shap.TreeExplainer for a LightGBM Booster."""

    def __init__(self, booster) -> None:
        import shap

        self._explainer = shap.TreeExplainer(booster)

    def contributions(self, features: pd.DataFrame) -> np.ndarray:
        """Return SHAP values shaped (n_rows, n_features), in margin space."""
        values = self._explainer.shap_values(features, check_additivity=False)
        if isinstance(values, list):
            # binary objective may return [class0, class1]
            values = values[-1]
        values = np.asarray(values)
        if values.ndim == 3:
            values = values[:, :, -1]
        return values


def shap_contributions(booster, features: pd.DataFrame) -> np.ndarray:
    return ShapExplainer(booster).contributions(features)


def top_factors(
    feature_row: pd.Series,
    contributions: np.ndarray,
    feature_names: list[str],
    top_n: int = 5,
    min_abs_contribution: float = 1e-4,
) -> tuple[list[dict], list[dict]]:
    """Split SHAP attributions into top positive and top negative drivers.

    Ties are broken by feature name so the output is deterministic.
    """
    records = []
    for name, contribution in zip(feature_names, contributions):
        contribution = float(contribution)
        if abs(contribution) < min_abs_contribution:
            continue
        value = feature_row[name]
        records.append(
            {
                "feature": name,
                "contribution": round(contribution, 6),
                "value": None if (isinstance(value, float) and np.isnan(value)) else _jsonable(value),
                "description": describe_feature(name, value),
            }
        )

    positive = sorted(
        [r for r in records if r["contribution"] > 0],
        key=lambda r: (-r["contribution"], r["feature"]),
    )[:top_n]
    negative = sorted(
        [r for r in records if r["contribution"] < 0],
        key=lambda r: (r["contribution"], r["feature"]),
    )[:top_n]
    return positive, negative


def _jsonable(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return round(float(value), 6)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value
