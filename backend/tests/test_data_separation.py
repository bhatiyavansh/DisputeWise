"""Guards the critical separation rule from the data-strategy upgrade:
data/locked/test/, data/generated/, data/reference/, and data/external/ must
never overlap or be mixable by accident.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
LOCKED_TEST_DIR = DATA_DIR / "locked" / "test"
GENERATED_DIR = DATA_DIR / "generated"
REFERENCE_DIR = DATA_DIR / "reference"
EXTERNAL_DIR = DATA_DIR / "external"
MANIFEST_PATH = DATA_DIR / "metadata" / "data_manifest.json"

# The synthetic dataset's own table filenames -- these must never appear
# under data/reference or data/external, since that would indicate someone
# merged synthetic/training rows into the domain-reference or external areas.
SYNTHETIC_TABLE_FILENAMES = {"customers.csv", "transactions.csv", "disputes.csv", "evidence.csv", "outcomes.csv"}


@pytest.mark.skipif(not REFERENCE_DIR.exists(), reason="data/reference not present in this checkout")
def test_reference_dir_contains_no_synthetic_table_files():
    present = {p.name for p in REFERENCE_DIR.glob("*.csv")}
    assert not (present & SYNTHETIC_TABLE_FILENAMES)


@pytest.mark.skipif(not EXTERNAL_DIR.exists(), reason="data/external not present in this checkout")
def test_external_dir_contains_no_synthetic_table_files():
    present = {p.name for p in EXTERNAL_DIR.rglob("*.csv")}
    assert not (present & SYNTHETIC_TABLE_FILENAMES)


@pytest.mark.skipif(not EXTERNAL_DIR.exists(), reason="data/external not present in this checkout")
def test_external_data_if_present_is_marked_benchmark_only():
    """If anything beyond the placeholder README has been added under
    data/external, every manifest.json in it must carry the
    EXTERNAL_BENCHMARK_ONLY marker (this repo currently has no such data --
    see docs/external_data.md -- so this test passes vacuously until then).
    """
    manifests = list(EXTERNAL_DIR.rglob("manifest.json"))
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text())
        status = manifest.get("status") or manifest.get("purpose") or ""
        assert "EXTERNAL_BENCHMARK_ONLY" in json.dumps(manifest), (
            f"{manifest_path} is missing the EXTERNAL_BENCHMARK_ONLY marker"
        )


@pytest.mark.skipif(not MANIFEST_PATH.exists(), reason="data manifest not present in this checkout")
def test_data_manifest_distinguishes_categories():
    manifest = json.loads(MANIFEST_PATH.read_text())
    datasets = manifest["datasets"]
    assert datasets["synthetic"]["purpose"] == "primary_ml_dataset"
    for entry in datasets["reference"]:
        assert entry["purpose"] == "domain_reference"
    assert datasets["external"]["purpose"] == "external_benchmark_only"


@pytest.mark.skipif(
    not (LOCKED_TEST_DIR.exists() and REFERENCE_DIR.exists()),
    reason="data/locked/test or data/reference not present in this checkout",
)
def test_locked_test_and_reference_directories_are_disjoint():
    locked_files = {p.name for p in LOCKED_TEST_DIR.glob("*")}
    reference_files = {p.name for p in REFERENCE_DIR.glob("*")}
    assert not (locked_files & reference_files)


@pytest.mark.skipif(
    not (GENERATED_DIR.exists() and REFERENCE_DIR.exists()),
    reason="data/generated or data/reference not present in this checkout",
)
def test_generated_and_reference_directories_are_disjoint():
    generated_files = {p.name for split in ("train", "validation", "test") for p in (GENERATED_DIR / split).glob("*")}
    reference_files = {p.name for p in REFERENCE_DIR.glob("*")}
    assert not (generated_files & reference_files)
