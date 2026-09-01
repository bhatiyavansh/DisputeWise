"""Tests for the new data/reference/ domain-knowledge layer added in the
Phase 1 data-strategy upgrade. This is NOT ML training data -- these tests
exist to guarantee it can never accidentally be treated as such.
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = REPO_ROOT / "data" / "reference"

pytestmark = pytest.mark.skipif(not REFERENCE_DIR.exists(), reason="data/reference not present in this checkout")

FORBIDDEN_FIELDS = {
    "favorable_outcome",
    "recovery_amount",
    "outcome_at",
    "outcome_source",
    "customer_id",
    "transaction_id",
    "dispute_id",
    "evidence_id",
    "password",
    "api_key",
    "secret",
    "credential",
    "token",
}


@pytest.fixture(scope="module")
def reason_codes() -> pd.DataFrame:
    return pd.read_csv(REFERENCE_DIR / "reason_codes.csv")


@pytest.fixture(scope="module")
def evidence_requirements() -> pd.DataFrame:
    return pd.read_csv(REFERENCE_DIR / "evidence_requirements.csv")


@pytest.fixture(scope="module")
def sources() -> list[dict]:
    return json.loads((REFERENCE_DIR / "sources.json").read_text())


def test_reference_files_exist():
    assert (REFERENCE_DIR / "reason_codes.csv").exists()
    assert (REFERENCE_DIR / "evidence_requirements.csv").exists()
    assert (REFERENCE_DIR / "sources.json").exists()


def test_minimum_reason_codes_present(reason_codes):
    ids = set(reason_codes["reason_code_id"])
    assert {"unauthorized_transaction", "goods_not_received", "duplicate_charge"} <= ids


def test_no_duplicate_reason_code_ids(reason_codes):
    assert reason_codes["reason_code_id"].duplicated().sum() == 0


def test_every_evidence_requirement_references_a_valid_reason_code(reason_codes, evidence_requirements):
    valid_ids = set(reason_codes["reason_code_id"])
    assert set(evidence_requirements["reason_code_id"]) <= valid_ids


def test_evidence_types_align_with_internal_taxonomy(evidence_requirements):
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from generate_dataset import ALL_EVIDENCE_TYPES

    assert set(evidence_requirements["evidence_type"]) <= set(ALL_EVIDENCE_TYPES)


def test_every_source_has_provenance(sources):
    required = {"source_id", "source_name", "source_url", "source_type", "license", "retrieved_at"}
    for source in sources:
        assert required <= set(source.keys()), source
        for field in required:
            assert str(source[field]).strip(), f"{source.get('source_id')} has an empty '{field}'"


def test_reference_data_has_no_outcome_labels(reason_codes, evidence_requirements):
    for df in (reason_codes, evidence_requirements):
        assert not (FORBIDDEN_FIELDS & set(c.lower() for c in df.columns))


def test_reference_data_has_no_recovery_amount_field(reason_codes, evidence_requirements):
    for df in (reason_codes, evidence_requirements):
        assert "recovery_amount" not in [c.lower() for c in df.columns]


def test_reference_data_has_no_customer_or_transaction_ids(reason_codes, evidence_requirements):
    for df in (reason_codes, evidence_requirements):
        cols = [c.lower() for c in df.columns]
        assert "customer_id" not in cols
        assert "transaction_id" not in cols


def test_reference_data_has_no_private_credentials(sources):
    blob = json.dumps(sources).lower()
    for term in ("password", "api_key", "secret", "credential", "token"):
        assert term not in blob


def test_verify_reference_data_script_passes():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_reference_data.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_verify_reference_data_script_does_not_modify_any_dataset():
    watched = list(REFERENCE_DIR.glob("*")) + [REPO_ROOT / "data" / "metadata" / "locked_test_metadata.json"]
    before = {p: p.read_bytes() for p in watched if p.is_file()}
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_reference_data.py")],
        capture_output=True,
        text=True,
    )
    after = {p: p.read_bytes() for p in watched if p.is_file()}
    assert before == after
