"""Guards for the data-strategy upgrade: the existing synthetic dataset and
locked test set must be provably untouched by anything added in this pass.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCKED_TEST_DIR = REPO_ROOT / "data" / "locked" / "test"
METADATA_PATH = REPO_ROOT / "data" / "metadata" / "locked_test_metadata.json"
GENERATED_DIR = REPO_ROOT / "data" / "generated"

# Frozen expectations recorded at the end of Phase 1 -- if these ever change,
# the locked test set has changed, which this upgrade must never do.
EXPECTED_CHECKSUM = "e1e8cd5054c92fd399c50fa733c0256ec05bea6c13c80a15165c7cd5d0693b5c"
EXPECTED_SEED = 42
EXPECTED_ROW_COUNTS = {
    "customers": 3544,
    "transactions": 7446,
    "disputes": 7446,
    "evidence": 119136,
    "outcomes": 7446,
}
EXPECTED_SPLIT_COUNTS = {"train": 35115, "validation": 7439, "test": 7446}


@pytest.mark.skipif(not METADATA_PATH.exists(), reason="locked test metadata not present in this checkout")
def test_locked_test_checksum_unchanged():
    metadata = json.loads(METADATA_PATH.read_text())
    assert metadata["checksum_sha256"] == EXPECTED_CHECKSUM
    assert metadata["generation_seed"] == EXPECTED_SEED
    assert metadata["row_counts"] == EXPECTED_ROW_COUNTS


@pytest.mark.skipif(not LOCKED_TEST_DIR.exists(), reason="locked test set not present in this checkout")
def test_verify_dataset_script_passes_without_error():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_dataset.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not LOCKED_TEST_DIR.exists(), reason="locked test set not present in this checkout")
def test_verify_dataset_script_does_not_modify_locked_files():
    before = {p.name: p.read_bytes() for p in sorted(LOCKED_TEST_DIR.glob("*.csv"))}
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_dataset.py")],
        capture_output=True,
        text=True,
    )
    after = {p.name: p.read_bytes() for p in sorted(LOCKED_TEST_DIR.glob("*.csv"))}
    assert before == after


@pytest.mark.skipif(not GENERATED_DIR.exists(), reason="data/generated not present in this checkout (gitignored)")
def test_train_validation_split_counts_unchanged():
    import csv

    for split, expected_count in EXPECTED_SPLIT_COUNTS.items():
        disputes_path = GENERATED_DIR / split / "disputes.csv"
        if not disputes_path.exists():
            pytest.skip(f"{disputes_path} not present in this checkout")
        with open(disputes_path) as f:
            actual_count = sum(1 for _ in csv.reader(f)) - 1  # minus header
        assert actual_count == expected_count, f"split '{split}' row count changed"


def test_generator_still_anchors_timestamps_to_a_fixed_reference():
    """Regression guard: an earlier bug used datetime.now() for relative
    timestamps inside the data-generation path, which made two runs with the
    identical seed produce byte-different CSVs. If this reappears, the
    dataset stops being reproducible and the lock's checksum becomes
    meaningless. This does not run the (expensive) generator -- it just
    proves the fix is still in place.
    """
    generator_src = (REPO_ROOT / "scripts" / "generate_dataset.py").read_text()
    assert "ANCHOR_NOW" in generator_src, "fixed-anchor timestamp mechanism appears to have been removed"

    # datetime.now(...) may only appear in run-provenance metadata (which is
    # allowed to reflect wall-clock time), never in customer/case generation.
    import ast

    tree = ast.parse(generator_src)
    offending_functions = {"generate_customers", "generate_cases"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in offending_functions:
            body_src = ast.get_source_segment(generator_src, node)
            assert "datetime.now(" not in body_src, (
                f"{node.name} calls datetime.now() directly -- this breaks reproducibility "
                "for a fixed seed. Use ANCHOR_NOW instead."
            )
