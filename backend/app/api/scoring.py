from fastapi import APIRouter, HTTPException

from app.schemas.common import NotImplementedResponse

router = APIRouter(tags=["scoring"])


@router.post("/cases/{case_id}/score", response_model=NotImplementedResponse, status_code=501)
def score_case(case_id: str) -> NotImplementedResponse:
    raise HTTPException(
        status_code=501,
        detail={
            "detail": "Winnability scoring is not implemented yet.",
            "phase": "Implemented in Phase 2 (Evidence Engine + ML Core).",
        },
    )
