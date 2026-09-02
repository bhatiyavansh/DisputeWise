from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.evidence_intel.versions import VERIFIER_VERSION
from app.schemas.evidence_intel import ClaimVerificationResponse, VerifyRequest, VerifyResponse
from app.services.evidence_intel_service import verify_case_claims
from app.services.scoring_service import CaseNotFoundError

router = APIRouter(tags=["evidence-intelligence"])


@router.post("/cases/{case_id}/verify", response_model=VerifyResponse)
def verify_case_response(case_id: str, request: VerifyRequest, db: Session = Depends(get_db)) -> VerifyResponse:
    """Independently verify a set of claims (e.g. a human-edited draft, or a
    draft generated elsewhere) against this case's own, freshly-rebuilt
    evidence packet and retrieved guidance.

    Deliberately decoupled from POST /draft's generation step -- this makes
    the verifier independently testable and reusable if a claim is edited
    after generation and needs re-checking before use. Uses exactly the same
    deterministic verifier as /draft; no LLM is involved.
    """
    try:
        _packet, _retrieval, verifications, response_state, reason = verify_case_claims(
            db, case_id, [c.model_dump() for c in request.claims]
        )
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    return VerifyResponse(
        case_id=case_id,
        verifier_version=VERIFIER_VERSION,
        claim_verifications=[ClaimVerificationResponse(**vars(c)) for c in verifications],
        response_state=response_state,
        response_state_reason=reason,
    )
