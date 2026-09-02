from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.evidence_intel.gap_analyzer import EvidenceGapResult
from app.schemas.evidence_intel import EvidenceGapResponse, GapItemResponse
from app.services.evidence_intel_service import get_case_gap
from app.services.scoring_service import CaseNotFoundError

router = APIRouter(tags=["evidence-intelligence"])


def _to_response(case_id: str, gap: EvidenceGapResult) -> EvidenceGapResponse:
    return EvidenceGapResponse(
        case_id=case_id,
        reason_code=gap.reason_code,
        schema_version=gap.schema_version,
        coverage={"required": gap.required_count, "available": gap.available_count, "missing": gap.missing_count},
        coverage_ratio=round(gap.coverage_ratio, 4),
        items=[GapItemResponse(**vars(item)) for item in gap.items],
    )


@router.post("/cases/{case_id}/evidence-gap", response_model=EvidenceGapResponse)
def evidence_gap_endpoint(case_id: str, db: Session = Depends(get_db)) -> EvidenceGapResponse:
    """Which evidence types this case's reason code requires (per authoritative
    reference guidance), which are on file, and how urgent each gap is.

    Deterministic: a pure function of the case's reason code + its evidence
    rows + the versioned data/reference/ tables. No ML, no LLM.
    """
    try:
        gap = get_case_gap(db, case_id)
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return _to_response(case_id, gap)
