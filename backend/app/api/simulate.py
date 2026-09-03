"""Phase 6 -- POST /simulate.

A separate endpoint on purpose: it never touches the production case
endpoints, never reads or writes the database, and returns a payload that is
explicitly marked as a scenario (`is_simulation`, `trace.persisted=false`) so
a simulated result can never be mistaken for a real merchant dispute.
"""

from fastapi import APIRouter, Depends

from app.api.evidence_gap import _to_response as gap_to_response
from app.api.scoring import get_risk_model
from app.decision.config import DecisionConfig, get_decision_config
from app.evidence_intel import versions as v
from app.evidence_intel.llm_provider import LLMProvider
from app.api.drafts import get_optional_llm_provider
from app.ml.model import RiskModel
from app.schemas.evidence_intel import (
    ClaimVerificationResponse,
    GeneratedClaimResponse,
    RetrievalResultResponse,
)
from app.schemas.simulation import (
    SimulationDecisionResponse,
    SimulationGenerationResponse,
    SimulationRequest,
    SimulationResponse,
    SimulationScoreResponse,
    SimulationTraceResponse,
)
from app.services.simulation_service import SimulationResult, run_simulation

router = APIRouter(tags=["simulation"])

DISCLAIMER = (
    "Scenario analysis on a hypothetical dispute. Not a real case, not persisted, and not a "
    "recommendation to act. Decision support only -- human approval is always required."
)


def _to_response(result: SimulationResult) -> SimulationResponse:
    generation = None
    if result.generation_ran:
        generation = SimulationGenerationResponse(
            response_state=result.response_state or v.GENERATION_UNAVAILABLE,
            response_state_reason=result.response_state_reason or "",
            generation_available=result.generation_available,
            summary=result.draft.summary if result.draft else None,
            response_body=result.draft.response_body if result.draft else None,
            claims=[GeneratedClaimResponse(**c.model_dump()) for c in result.draft.claims] if result.draft else [],
            claim_verifications=[ClaimVerificationResponse(**vars(c)) for c in result.verifications],
            missing_evidence=result.draft.missing_evidence if result.draft else [],
        )

    return SimulationResponse(
        simulation_id=result.simulation_id,
        reason_code=result.reason_code,
        score=SimulationScoreResponse(
            raw_probability=result.score["raw_probability"],
            calibrated_probability=result.score["calibrated_probability"],
            risk_band=result.score["risk_band"],
            calibration_method=result.score["calibration_method"],
            top_positive_factors=result.score["top_positive_factors"],
            top_negative_factors=result.score["top_negative_factors"],
            evidence_summary=result.score["evidence_summary"],
        ),
        decision=SimulationDecisionResponse(
            decision=result.decision["decision"],
            reason=result.decision["reason"],
            decision_policy_version=result.decision["decision_policy_version"],
            evidence_gap_downgrade=result.decision["evidence_gap_downgrade"],
            dispute_amount=result.decision["dispute_amount"],
            recovery_rate=result.decision["recovery_rate"],
            recoverable_amount=result.decision["recoverable_amount"],
            contest_cost=result.decision["contest_cost"],
            expected_recovery=result.decision["expected_recovery"],
            expected_net_value=result.decision["expected_net_value"],
            break_even_probability=result.decision["break_even_probability"],
            break_even_explanation=result.decision["break_even_explanation"],
            sensitivity=result.decision["sensitivity"],
        ),
        evidence_gap=gap_to_response(result.simulation_id, result.gap),
        retrieved_sources=[RetrievalResultResponse(**vars(r)) for r in result.retrieval_results],
        generation=generation,
        trace=SimulationTraceResponse(
            simulation_id=result.simulation_id,
            model_version=result.score["model_version"],
            feature_schema_version=result.score["feature_schema_version"],
            decision_policy_version=result.decision["decision_policy_version"],
            evidence_schema_version=result.gap.schema_version,
            knowledge_base_version=v.KNOWLEDGE_BASE_VERSION,
            retrieval_config_version=v.RETRIEVAL_CONFIG_VERSION,
            # Only reported when the stage they describe actually ran.
            prompt_version=v.PROMPT_VERSION if result.draft else None,
            response_schema_version=v.RESPONSE_SCHEMA_VERSION if result.draft else None,
            verifier_version=v.VERIFIER_VERSION if result.verifications else None,
            retrieved_source_ids=sorted({r.source_id for r in result.retrieval_results}),
            retrieved_chunk_ids=sorted({r.chunk_id for r in result.retrieval_results}),
            generated_at=result.generated_at,
            persisted=False,
        ),
        disclaimer=DISCLAIMER,
    )


@router.post("/simulate", response_model=SimulationResponse)
def simulate(
    request: SimulationRequest,
    model: RiskModel = Depends(get_risk_model),
    decision_config: DecisionConfig = Depends(get_decision_config),
    llm_provider: LLMProvider | None = Depends(get_optional_llm_provider),
) -> SimulationResponse:
    """Score, decide, and analyze a hypothetical dispute without storing it.

    Runs the same pipeline as a real case -- the same leakage-safe feature
    builder, the same risk-v1 model and calibration, the same decision-v1
    policy, the same evidence-gap analyzer and retrieval, and (opt-in, via
    `generate_response`) the same generation + deterministic verifier.

    No outcome/target field is accepted (see app/schemas/simulation.py), and
    nothing is written to the database.
    """
    result = run_simulation(
        request,
        risk_model=model,
        decision_config=decision_config,
        llm_provider=llm_provider,
    )
    return _to_response(result)
