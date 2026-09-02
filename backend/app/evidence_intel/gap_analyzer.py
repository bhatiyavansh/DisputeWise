"""Part A -- Evidence Gap Analyzer.

Pure function of (reason_code, case evidence state) + the versioned
data/reference/ tables -- no case-specific hardcoding, no DB access here
(that lives in the thin service wrapper at the bottom). Determines, per
reason code, which evidence types are REQUIRED (per authoritative reference
guidance), which of those are AVAILABLE vs MISSING for this specific case,
and how urgently each gap should be closed.

"Required" = reference-data relevance in {high, medium} for this reason
code -- deliberately excludes "low" relevance types from the coverage
denominator (they're still reported, just not counted as gaps), matching
the same high/medium/low distinction already used by Phase 1's evidence
taxonomy and Phase 2/3's evidence_summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.evidence_intel import versions as v
from app.evidence_intel.reference_data import ReferenceData, load_reference_data

REQUIRED_RELEVANCE_LEVELS = frozenset({"high", "medium"})

_RELEVANCE_LABEL = {"high": v.RELEVANCE_HIGH, "medium": v.RELEVANCE_MEDIUM, "low": v.RELEVANCE_LOW}


@dataclass(frozen=True)
class CaseEvidenceState:
    """The minimal per-evidence-type state the analyzer needs about a case.

    Deliberately narrow (not the ORM row) so this module stays a pure
    function, easy to unit test without a database.
    """

    evidence_type: str
    available: bool
    strength: float
    evidence_id: str | None = None


@dataclass(frozen=True)
class GapItem:
    evidence_type: str
    required: bool
    status: str  # AVAILABLE | MISSING
    relevance: str  # HIGH | MEDIUM | LOW
    priority: str  # CRITICAL | IMPORTANT | OPTIONAL | NONE
    reason: str
    source_id: str
    strength: float
    evidence_id: str | None


@dataclass(frozen=True)
class EvidenceGapResult:
    reason_code: str
    schema_version: str
    required_count: int
    available_count: int
    missing_count: int
    items: list[GapItem] = field(default_factory=list)

    @property
    def coverage_ratio(self) -> float:
        return self.available_count / self.required_count if self.required_count else 1.0

    @property
    def missing_critical(self) -> list[GapItem]:
        return [i for i in self.items if i.status == v.STATUS_MISSING and i.priority == v.PRIORITY_CRITICAL]

    @property
    def has_critical_gap(self) -> bool:
        return len(self.missing_critical) > 0


def _priority_for(relevance: str, status: str) -> str:
    if status == v.STATUS_AVAILABLE:
        return v.PRIORITY_NONE
    return {"high": v.PRIORITY_CRITICAL, "medium": v.PRIORITY_IMPORTANT, "low": v.PRIORITY_OPTIONAL}[relevance]


def analyze_gap(
    reason_code: str,
    case_evidence: dict[str, CaseEvidenceState],
    reference: ReferenceData | None = None,
) -> EvidenceGapResult:
    """Analyze evidence coverage for one case against reference requirements.

    `case_evidence` is keyed by evidence_type; a type absent from the dict is
    treated the same as `available=False` (evidence genuinely not on file).
    """
    reference = reference or load_reference_data()
    requirements = reference.requirements_for(reason_code)
    if not requirements:
        raise ValueError(f"no reference evidence requirements found for reason_code '{reason_code}'")

    items: list[GapItem] = []
    for requirement in sorted(requirements, key=lambda r: r.evidence_type):
        state = case_evidence.get(requirement.evidence_type)
        available = bool(state and state.available)
        status = v.STATUS_AVAILABLE if available else v.STATUS_MISSING
        relevance_label = _RELEVANCE_LABEL[requirement.relevance]
        required = requirement.relevance in REQUIRED_RELEVANCE_LEVELS

        items.append(
            GapItem(
                evidence_type=requirement.evidence_type,
                required=required,
                status=status,
                relevance=relevance_label,
                priority=_priority_for(requirement.relevance, status) if required else v.PRIORITY_NONE,
                reason=requirement.description,
                source_id=requirement.source_id,
                strength=state.strength if state else 0.0,
                evidence_id=state.evidence_id if state else None,
            )
        )

    required_items = [i for i in items if i.required]
    available_count = sum(1 for i in required_items if i.status == v.STATUS_AVAILABLE)

    return EvidenceGapResult(
        reason_code=reason_code,
        schema_version=v.EVIDENCE_SCHEMA_VERSION,
        required_count=len(required_items),
        available_count=available_count,
        missing_count=len(required_items) - available_count,
        items=items,
    )


# ---------------------------------------------------------------------------
# DB-aware convenience wrapper
# ---------------------------------------------------------------------------


def case_evidence_state_from_rows(evidence_rows: list) -> dict[str, CaseEvidenceState]:
    """Build the analyzer's input from ORM Evidence rows (app.models.evidence.Evidence)."""
    return {
        row.evidence_type: CaseEvidenceState(
            evidence_type=row.evidence_type,
            available=bool(row.available),
            strength=float(row.strength or 0.0),
            evidence_id=row.evidence_id,
        )
        for row in evidence_rows
    }
