from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.evidence_gap import _to_response as gap_to_response
from app.api.scoring import get_risk_model
from app.db.session import get_db
from app.decision.config import DecisionConfig, get_decision_config
from app.evidence_intel.llm_provider import LLMProvider, get_llm_provider
from app.ml.model import RiskModel
from app.schemas.evidence_intel import (
    ClaimVerificationResponse,
    DecisionSummaryResponse,
    DraftResponse,
    GeneratedClaimResponse,
    ResponseTraceResponse,
    RetrievalResultResponse,
)
from app.services.evidence_intel_service import DraftResult, generate_case_draft
from app.services.scoring_service import CaseNotFoundError

router = APIRouter(tags=["evidence-intelligence"])


def get_optional_llm_provider() -> LLMProvider | None:
    """Unlike get_risk_model, this never raises -- an unconfigured LLM
    provider is a normal, expected state (see app/evidence_intel/llm_provider.py),
    not a server error. The endpoint reports it via `response_state`
    (GENERATION_UNAVAILABLE) instead of an HTTP error status."""
    return get_llm_provider()


def _to_response(result: DraftResult) -> DraftResponse:
    return DraftResponse(
        case_id=result.case_id,
        reason_code=result.reason_code,
        model_version=result.trace.model_version,
        feature_schema_version=result.trace.feature_schema_version,
        decision_policy_version=result.trace.decision_policy_version,
        evidence_schema_version=result.trace.evidence_schema_version,
        knowledge_base_version=result.trace.knowledge_base_version,
        prompt_version=result.trace.prompt_version,
        response_schema_version=result.trace.response_schema_version,
        verifier_version=result.trace.verifier_version,
        decision=(
            DecisionSummaryResponse(
                decision=result.decision["decision"],
                calibrated_probability=result.decision["calibrated_probability"],
                expected_net_value=result.decision["expected_net_value"],
                risk_band=result.decision["risk_band"],
            )
            if result.decision
            else None
        ),
        evidence_gap=gap_to_response(result.case_id, result.packet.gap),
        retrieved_sources=[RetrievalResultResponse(**vars(r)) for r in result.retrieval_results],
        generation_available=result.generation_available,
        summary=result.draft.summary if result.draft else None,
        claims=[GeneratedClaimResponse(**c.model_dump()) for c in result.draft.claims] if result.draft else [],
        missing_evidence=result.draft.missing_evidence if result.draft else [],
        response_body=result.draft.response_body if result.draft else None,
        claim_verifications=[ClaimVerificationResponse(**vars(c)) for c in result.verifications],
        response_state=result.response_state,
        response_state_reason=result.response_state_reason,
        generation_error_kind=result.generation_error_kind,
        trace=ResponseTraceResponse(**vars(result.trace)),
    )


@router.post("/cases/{case_id}/draft", response_model=DraftResponse)
def draft_case_response(
    case_id: str,
    top_k: int = Query(default=6, ge=1, le=20, description="number of retrieved guidance chunks"),
    db: Session = Depends(get_db),
    model: RiskModel = Depends(get_risk_model),
    decision_config: DecisionConfig = Depends(get_decision_config),
    llm_provider: LLMProvider | None = Depends(get_optional_llm_provider),
) -> DraftResponse:
    """Evidence-grounded dispute-response draft: decision (reused from Phase 3)
    + evidence gap + retrieved authoritative guidance + a structured,
    claim-level-verified response draft.

    Every material claim is checked against this case's own evidence and the
    retrieved guidance before this endpoint returns -- an unsupported or
    invalidly-referenced claim sets `response_state` to DRAFT_BLOCKED rather
    than being silently included. If no LLM provider is configured,
    `response_state` is GENERATION_UNAVAILABLE and `generation_available` is
    false, but decision/evidence-gap/retrieval are still returned in full.

    This endpoint NEVER submits, sends, or transmits anything -- see
    `disclaimer`. Human approval is always required.
    """
    try:
        result = generate_case_draft(
            db, case_id, risk_model=model, decision_config=decision_config, llm_provider=llm_provider, top_k_retrieval=top_k
        )
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return _to_response(result)
