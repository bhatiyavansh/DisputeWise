"""Feature schema, versioning, and leakage policy for the Phase 2 risk model.

This module is the single source of truth for:
  - model / feature schema versions
  - the evidence taxonomy the feature builder pivots over
  - which raw columns are ALLOWED to become features (an allowlist, not a blacklist)
  - which raw columns are explicitly FORBIDDEN (a redundant second guard)
  - risk-band thresholds
  - artifact locations

Leakage policy
--------------
The primary defense against target leakage is structural rather than
declarative: `features.build_features()` does not accept the `outcomes`
table as a parameter at all, so no outcome column (`favorable_outcome`,
`recovery_amount`, `outcome_at`, `outcome_source`) can physically reach the
feature matrix. The allowlist and forbidden-column set below are a second
and third layer on top of that.
"""

from __future__ import annotations

import os
from pathlib import Path

MODEL_VERSION = "risk-v1"
FEATURE_SCHEMA_VERSION = "features-v1"
DATASET_VERSION = "disputewise_synthetic_v1"

# ---------------------------------------------------------------------------
# Evidence taxonomy (mirrors the Phase 1 evidence schema; see docs/phase1.md).
# Ordering is fixed because it determines generated feature-column ordering.
# ---------------------------------------------------------------------------
AUTHENTICATION_EVIDENCE = ("three_ds", "avs", "cvv", "device_match", "ip_match")
FULFILLMENT_EVIDENCE = (
    "delivery_confirmed",
    "tracking_available",
    "delivery_address_match",
    "delivery_timestamp",
    "proof_of_delivery",
)
CUSTOMER_EVIDENCE = ("prior_order_history", "prior_successful_orders", "prior_disputes")
COMMUNICATION_EVIDENCE = (
    "customer_communication_available",
    "cancellation_request",
    "refund_request",
)

ALL_EVIDENCE_TYPES = (
    AUTHENTICATION_EVIDENCE + FULFILLMENT_EVIDENCE + CUSTOMER_EVIDENCE + COMMUNICATION_EVIDENCE
)

EVIDENCE_CATEGORIES = {
    "authentication": AUTHENTICATION_EVIDENCE,
    "fulfillment": FULFILLMENT_EVIDENCE,
    "customer": CUSTOMER_EVIDENCE,
    "communication": COMMUNICATION_EVIDENCE,
}

# How to turn each evidence row's JSON `value` into a numeric signal.
# Key = evidence_type, value = (json_key, kind). kind is "bool", "count",
# "equals:<X>" (categorical match), or "timestamp".
EVIDENCE_VALUE_SPEC: dict[str, tuple[str, str]] = {
    "three_ds": ("authenticated", "bool"),
    "avs": ("result", "equals:Y"),
    "cvv": ("result", "equals:M"),
    "device_match": ("match", "bool"),
    "ip_match": ("match", "bool"),
    "delivery_confirmed": ("confirmed", "bool"),
    "tracking_available": ("available", "bool"),
    "delivery_address_match": ("match", "bool"),
    "delivery_timestamp": ("timestamp", "timestamp"),
    "proof_of_delivery": ("present", "bool"),
    "prior_order_history": ("order_count", "count"),
    "prior_successful_orders": ("count", "count"),
    "prior_disputes": ("count", "count"),
    "customer_communication_available": ("present", "bool"),
    "cancellation_request": ("requested", "bool"),
    "refund_request": ("requested", "bool"),
}

# Evidence types whose parsed value is a magnitude rather than a 0/1 flag.
NON_BINARY_EVIDENCE_VALUES = frozenset(
    {"prior_order_history", "prior_successful_orders", "prior_disputes", "delivery_timestamp"}
)

STRONG_EVIDENCE_STRENGTH_THRESHOLD = 0.6

# ---------------------------------------------------------------------------
# Raw-column policy
# ---------------------------------------------------------------------------

# Raw source columns the feature builder is permitted to read. Anything not
# listed here is never touched, regardless of what a future dataset adds.
ALLOWED_SOURCE_COLUMNS: dict[str, frozenset[str]] = {
    "disputes": frozenset({"dispute_id", "transaction_id", "reason_code", "dispute_amount", "created_at", "response_deadline"}),
    "transactions": frozenset(
        {
            "transaction_id",
            "customer_id",
            "amount",
            "payment_method",
            "created_at",
            "captured_at",
            "status",
            "billing_address_id",
            "shipping_address_id",
            "avs_result",
            "cvv_result",
            "three_ds_authenticated",
        }
    ),
    "customers": frozenset(
        {
            "customer_id",
            "account_age_days",
            "previous_order_count",
            "previous_successful_order_count",
            "previous_dispute_count",
            "previous_refund_count",
        }
    ),
    "evidence": frozenset({"dispute_id", "evidence_type", "available", "value", "relevance", "strength"}),
}

# Columns that must NEVER appear as, or contribute to, a model feature.
# Each entry records why, so the exclusion is auditable rather than folklore.
FORBIDDEN_COLUMNS: dict[str, str] = {
    # --- target / outcome (structurally unreachable: outcomes table is never
    # passed to build_features, but named here as a defense in depth) ---
    "favorable_outcome": "the prediction target",
    "recovery_amount": "perfect target proxy -- non-null iff favorable_outcome is True",
    "outcome_at": "post-outcome timestamp; unknown at scoring time",
    "outcome_source": "post-outcome provenance; unknown at scoring time",
    # --- generator-time labels ---
    "scenario_archetype": "synthetic-generator label; unknowable for a real incoming dispute",
    "split": "data-management field, not a case attribute",
    # --- identifiers (high-cardinality; no legitimate generalization) ---
    "dispute_id": "identifier",
    "transaction_id": "identifier",
    "customer_id": "identifier (also the split key -- would enable memorization)",
    "evidence_id": "identifier",
    "merchant_id": "identifier; uniformly random in the synthetic generator (zero signal by construction)",
    "device_id": "raw identifier -- used only via the derived device_match evidence signal",
    "ip_address": "raw identifier -- used only via the derived ip_match evidence signal",
    "billing_address_id": "raw identifier -- used only via the derived billing_shipping_match flag",
    "shipping_address_id": "raw identifier -- used only via the derived billing_shipping_match flag",
    # --- fairness ---
    "country": "national-origin proxy; excluded on fairness grounds (and carries no signal by construction)",
    # --- not available / not meaningful at scoring time ---
    "status_dispute": "dispute workflow state; in production correlates with post-decision information",
    "currency": "single-valued (INR) in this dataset -- zero variance",
    "account_created_at": "redundant with account_age_days; absolute dates invite calendar overfitting",
}

# Columns the feature builder is allowed to READ but which must never survive
# as a feature themselves: join keys, and raw identifiers that exist only to
# derive a comparison (e.g. billing vs. shipping address equality).
DERIVED_ONLY_COLUMNS = frozenset(
    {
        # join keys
        "dispute_id",
        "transaction_id",
        "customer_id",
        # read solely to compute billing_shipping_match
        "billing_address_id",
        "shipping_address_id",
    }
)

# ---------------------------------------------------------------------------
# Categorical features (LightGBM native categorical handling)
# ---------------------------------------------------------------------------
CATEGORICAL_FEATURES: dict[str, tuple[str, ...]] = {
    "reason_code": ("unauthorized_transaction", "goods_not_received", "duplicate_charge"),
    "payment_method": ("card", "upi", "netbanking"),
    "transaction_status": ("captured", "refunded", "failed"),
    "avs_result": ("Y", "N", "U", "M"),
    "cvv_result": ("M", "N", "U"),
}

# Sentinel used for a categorical value not seen in the declared vocabulary.
UNKNOWN_CATEGORY_CODE = -1

# ---------------------------------------------------------------------------
# Risk bands
#
# These describe the MODEL'S CONFIDENCE that contesting yields a favorable
# outcome. They are deliberately NOT economic recommendations -- expected
# recovery vs. contest cost is Phase 3 and is not implemented here.
# ---------------------------------------------------------------------------
RISK_BAND_HIGH_THRESHOLD = 0.70
RISK_BAND_LOW_THRESHOLD = 0.40

RISK_BAND_HIGH = "HIGH_WINNABILITY"
RISK_BAND_MEDIUM = "MEDIUM_WINNABILITY"
RISK_BAND_LOW = "LOW_WINNABILITY"


def risk_band(calibrated_probability: float) -> str:
    """Map a calibrated probability to a coarse winnability band."""
    if calibrated_probability >= RISK_BAND_HIGH_THRESHOLD:
        return RISK_BAND_HIGH
    if calibrated_probability < RISK_BAND_LOW_THRESHOLD:
        return RISK_BAND_LOW
    return RISK_BAND_MEDIUM


# ---------------------------------------------------------------------------
# Artifact locations
# ---------------------------------------------------------------------------


def artifacts_dir() -> Path:
    """Resolve the artifacts root.

    Honors DISPUTEWISE_ARTIFACTS_DIR, then the container mount (/artifacts),
    then falls back to <repo_root>/artifacts for host-side runs.
    """
    env = os.environ.get("DISPUTEWISE_ARTIFACTS_DIR")
    if env:
        return Path(env)
    container_path = Path("/artifacts")
    if container_path.is_dir():
        return container_path
    return Path(__file__).resolve().parents[3] / "artifacts"


def models_dir() -> Path:
    return artifacts_dir() / "models"


def evaluation_dir() -> Path:
    return artifacts_dir() / "evaluation"


MODEL_FILENAME = "risk_model.txt"
FEATURE_SCHEMA_FILENAME = "feature_schema.json"
MODEL_CONFIG_FILENAME = "model_config.json"
TRAINING_METRICS_FILENAME = "training_metrics.json"
CALIBRATOR_FILENAME = "calibrator.json"
