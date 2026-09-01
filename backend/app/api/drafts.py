from fastapi import APIRouter, HTTPException

from app.schemas.common import NotImplementedResponse

router = APIRouter(tags=["drafts"])


@router.post("/cases/{case_id}/draft", response_model=NotImplementedResponse, status_code=501)
def draft_case_response(case_id: str) -> NotImplementedResponse:
    raise HTTPException(
        status_code=501,
        detail={
            "detail": "Evidence-grounded response drafting is not implemented yet.",
            "phase": "Implemented in Phase 4 (RAG + LLM Response Generator).",
        },
    )
