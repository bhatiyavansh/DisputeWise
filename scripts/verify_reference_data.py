#!/usr/bin/env python3
"""Validate data/reference/ -- the public domain-knowledge reference layer.

This is deliberately separate from scripts/verify_dataset.py: that script
validates the synthetic ML dataset (data/locked/test/); this one validates
the reference layer (reason codes / evidence requirements / sources), which
is domain knowledge for grounding the generator and for Phase 4's future RAG
corpus -- NOT training data, and NOT an ML dataset.

Checks:
  - required columns are present in reason_codes.csv / evidence_requirements.csv / sources.json
  - no duplicate reason_code_id values
  - every evidence_requirements row references a reason_code_id that exists
  - every source_id referenced anywhere resolves to an entry in sources.json
  - every sources.json entry has complete provenance
  - source_url values are syntactically valid URLs
  - evidence_type values belong to our internal evidence taxonomy
  - reference data contains no ML outcome/target fields and no case-level
    identifiers (this is domain knowledge, not labeled training data)

Exits non-zero on any failure.

Usage:
    python scripts/verify_reference_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset_common import DATA_DIR  # noqa: E402
from generate_dataset import ALL_EVIDENCE_TYPES, REASON_CODES  # noqa: E402

REFERENCE_DIR = DATA_DIR / "reference"

REQUIRED_REASON_CODE_COLUMNS = {"reason_code_id", "reason_code_name", "description", "category", "source_id"}
REQUIRED_EVIDENCE_REQ_COLUMNS = {"reason_code_id", "evidence_type", "relevance", "description", "source_id"}
REQUIRED_SOURCE_FIELDS = {"source_id", "source_name", "source_url", "source_type", "license", "retrieved_at"}

VALID_RELEVANCE = {"high", "medium", "low"}

# Fields that would indicate someone accidentally merged ML training/label
# data into the reference layer. None of these belong in domain-reference CSVs.
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


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except ValueError:
        return False


def main() -> None:
    reason_codes_path = REFERENCE_DIR / "reason_codes.csv"
    evidence_req_path = REFERENCE_DIR / "evidence_requirements.csv"
    sources_path = REFERENCE_DIR / "sources.json"

    for path in (reason_codes_path, evidence_req_path, sources_path):
        if not path.exists():
            fail(f"missing required reference file: {path}")

    reason_codes = pd.read_csv(reason_codes_path)
    evidence_req = pd.read_csv(evidence_req_path)
    sources = json.loads(sources_path.read_text())

    # ---- forbidden fields (no ML labels / no case-level identifiers) ----
    for name, df in [("reason_codes.csv", reason_codes), ("evidence_requirements.csv", evidence_req)]:
        present_forbidden = FORBIDDEN_FIELDS & set(c.lower() for c in df.columns)
        if present_forbidden:
            fail(f"{name} contains forbidden ML-label/identifier/credential fields: {present_forbidden}")
    sources_text = json.dumps(sources).lower()
    for forbidden in FORBIDDEN_FIELDS:
        if forbidden in sources_text:
            fail(f"sources.json appears to reference a forbidden field/term: '{forbidden}'")
    print("OK: no ML outcome labels, case identifiers, or credential-like fields present")

    # ---- schema ----
    missing_rc_cols = REQUIRED_REASON_CODE_COLUMNS - set(reason_codes.columns)
    if missing_rc_cols:
        fail(f"reason_codes.csv missing required columns: {missing_rc_cols}")
    missing_evd_cols = REQUIRED_EVIDENCE_REQ_COLUMNS - set(evidence_req.columns)
    if missing_evd_cols:
        fail(f"evidence_requirements.csv missing required columns: {missing_evd_cols}")
    if not isinstance(sources, list) or not sources:
        fail("sources.json must be a non-empty JSON array")
    print("OK: required columns/structure present")

    # ---- duplicates ----
    dupes = reason_codes["reason_code_id"].duplicated().sum()
    if dupes:
        fail(f"reason_codes.csv has {dupes} duplicate reason_code_id values")
    print("OK: no duplicate reason_code_id values")

    # ---- referential integrity: evidence -> reason code ----
    valid_reason_ids = set(reason_codes["reason_code_id"])
    bad_refs = set(evidence_req["reason_code_id"]) - valid_reason_ids
    if bad_refs:
        fail(f"evidence_requirements.csv references unknown reason_code_id(s): {bad_refs}")
    print("OK: every evidence requirement references a valid reason code")

    # ---- our internal reason-code taxonomy is covered ----
    missing_reason_codes = set(REASON_CODES) - valid_reason_ids
    if missing_reason_codes:
        fail(f"reason_codes.csv is missing our internal reason codes: {missing_reason_codes}")
    print(f"OK: minimum reason codes present ({sorted(REASON_CODES)})")

    # ---- evidence taxonomy alignment ----
    bad_evidence_types = set(evidence_req["evidence_type"]) - set(ALL_EVIDENCE_TYPES)
    if bad_evidence_types:
        fail(f"evidence_requirements.csv uses evidence_type(s) outside our internal taxonomy: {bad_evidence_types}")
    bad_relevance = set(evidence_req["relevance"]) - VALID_RELEVANCE
    if bad_relevance:
        fail(f"evidence_requirements.csv has invalid relevance value(s): {bad_relevance}")
    print("OK: evidence_type/relevance values align with our internal taxonomy")

    # ---- provenance ----
    for source in sources:
        missing_fields = REQUIRED_SOURCE_FIELDS - set(source.keys())
        if missing_fields:
            fail(f"sources.json entry {source.get('source_id', '<unknown>')} missing provenance fields: {missing_fields}")
        for field in REQUIRED_SOURCE_FIELDS:
            if not str(source.get(field, "")).strip():
                fail(f"sources.json entry {source.get('source_id')} has an empty provenance field: '{field}'")
        if not is_valid_url(source["source_url"]):
            fail(f"sources.json entry {source['source_id']} has a syntactically invalid source_url: {source['source_url']}")
    print("OK: every source has complete provenance and a syntactically valid URL")

    # ---- every source_id referenced by the CSVs resolves ----
    valid_source_ids = {s["source_id"] for s in sources}
    for name, df in [("reason_codes.csv", reason_codes), ("evidence_requirements.csv", evidence_req)]:
        bad_source_ids = set(df["source_id"]) - valid_source_ids
        if bad_source_ids:
            fail(f"{name} references source_id(s) not present in sources.json: {bad_source_ids}")
    print("OK: every referenced source_id resolves to sources.json")

    print("\nReference data verification PASSED.")


if __name__ == "__main__":
    main()
