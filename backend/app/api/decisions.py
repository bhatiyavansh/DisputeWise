from fastapi import APIRouter, HTTPException

from app.schemas.common import NotImplementedResponse

router = APIRouter(tags=["decisions"])


@router.post("/cases/{case_id}/decision", response_model=NotImplementedResponse, status_code=501)
def decide_case(case_id: str) -> NotImplementedResponse:
    raise HTTPException(
        status_code=501,
        detail={
            "detail": "Contest/no-contest decisioning is not implemented yet.",
            "phase": "Implemented in Phase 3 (Cost-Sensitive Decision Engine).",
        },
    )
