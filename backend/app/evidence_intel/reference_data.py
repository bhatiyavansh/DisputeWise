"""Loads data/reference/ -- the Phase 1 domain-knowledge layer -- for use by
the evidence gap analyzer and the RAG knowledge base.

This is a READ-ONLY loader. It never writes to data/reference/, never mixes
this data with ML training data (data/generated/, data/locked/test/), and
never treats reference rows as ML features or outcome labels -- see
docs/data_strategy.md for why that separation exists and
scripts/verify_reference_data.py for how it's enforced at the data layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd


def _repo_root() -> Path:
    # backend/app/evidence_intel/reference_data.py -> backend/app -> backend -> repo root
    # Mirrors the container-mount-topology trick used by app/ml/data.py: works
    # both on host (backend/ sibling of data/) and in the container (both
    # mounted as siblings under /).
    candidate = Path("/data/reference")
    if candidate.is_dir():
        return Path("/")
    return Path(__file__).resolve().parents[3]


def reference_dir() -> Path:
    return _repo_root() / "data" / "reference"


@dataclass(frozen=True)
class ReasonCodeInfo:
    reason_code_id: str
    reason_code_name: str
    description: str
    category: str
    network_examples: str
    source_id: str


@dataclass(frozen=True)
class EvidenceRequirement:
    reason_code_id: str
    evidence_type: str
    relevance: str  # "high" | "medium" | "low"
    description: str
    source_id: str


@dataclass(frozen=True)
class Source:
    source_id: str
    source_name: str
    source_url: str
    source_type: str
    license: str
    retrieved_at: str


@dataclass(frozen=True)
class ReferenceData:
    reason_codes: dict[str, ReasonCodeInfo]
    evidence_requirements: list[EvidenceRequirement]
    sources: dict[str, Source]

    def requirements_for(self, reason_code_id: str) -> list[EvidenceRequirement]:
        return [r for r in self.evidence_requirements if r.reason_code_id == reason_code_id]

    def source(self, source_id: str) -> Source | None:
        return self.sources.get(source_id)


@lru_cache(maxsize=1)
def load_reference_data() -> ReferenceData:
    directory = reference_dir()

    reason_codes_df = pd.read_csv(directory / "reason_codes.csv")
    evidence_df = pd.read_csv(directory / "evidence_requirements.csv")
    sources_raw = json.loads((directory / "sources.json").read_text())

    reason_codes = {
        row["reason_code_id"]: ReasonCodeInfo(
            reason_code_id=row["reason_code_id"],
            reason_code_name=row["reason_code_name"],
            description=row["description"],
            category=row["category"],
            network_examples=row["network_examples"],
            source_id=row["source_id"],
        )
        for _, row in reason_codes_df.iterrows()
    }

    evidence_requirements = [
        EvidenceRequirement(
            reason_code_id=row["reason_code_id"],
            evidence_type=row["evidence_type"],
            relevance=row["relevance"],
            description=row["description"],
            source_id=row["source_id"],
        )
        for _, row in evidence_df.iterrows()
    ]

    sources = {
        entry["source_id"]: Source(
            source_id=entry["source_id"],
            source_name=entry["source_name"],
            source_url=entry["source_url"],
            source_type=entry["source_type"],
            license=entry["license"],
            retrieved_at=entry["retrieved_at"],
        )
        for entry in sources_raw
    }

    return ReferenceData(reason_codes=reason_codes, evidence_requirements=evidence_requirements, sources=sources)
