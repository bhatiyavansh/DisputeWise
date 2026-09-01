"""Shared constants/paths used by generate_dataset.py, load_database.py and verify_dataset.py."""

from pathlib import Path

# Works both on host (scripts/ sibling of data/ under repo root) and in the
# backend container (docker-compose mounts ./scripts -> /scripts, ./data -> /data,
# both siblings under container root).
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
GENERATED_DIR = DATA_DIR / "generated"
LOCKED_TEST_DIR = DATA_DIR / "locked" / "test"
METADATA_DIR = DATA_DIR / "metadata"

TABLES = ["customers", "transactions", "disputes", "evidence", "outcomes"]
SPLITS = ["train", "validation", "test"]

DATASET_SCHEMA_VERSION = "1.0.0"

# customers.csv
CUSTOMER_COLUMNS = [
    "customer_id",
    "account_created_at",
    "country",
    "account_age_days",
    "previous_order_count",
    "previous_successful_order_count",
    "previous_dispute_count",
    "previous_refund_count",
    "split",
]

# transactions.csv
TRANSACTION_COLUMNS = [
    "transaction_id",
    "customer_id",
    "merchant_id",
    "amount",
    "currency",
    "payment_method",
    "created_at",
    "captured_at",
    "status",
    "device_id",
    "ip_address",
    "billing_address_id",
    "shipping_address_id",
    "avs_result",
    "cvv_result",
    "three_ds_authenticated",
    "split",
]

# disputes.csv (the "case" table)
DISPUTE_COLUMNS = [
    "dispute_id",
    "transaction_id",
    "reason_code",
    "dispute_amount",
    "created_at",
    "response_deadline",
    "status",
    "scenario_archetype",
    "split",
]

# evidence.csv
EVIDENCE_COLUMNS = [
    "evidence_id",
    "dispute_id",
    "evidence_type",
    "available",
    "value",
    "relevance",
    "strength",
    "created_at",
    "split",
]

# outcomes.csv
OUTCOME_COLUMNS = [
    "dispute_id",
    "favorable_outcome",
    "outcome_at",
    "outcome_source",
    "recovery_amount",
    "split",
]
