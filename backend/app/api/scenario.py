"""Phase 7A -- POST /cases/{case_id}/evidence-scenario.

Read-only: it loads the case, evaluates it twice (as-is and under the
requested evidence changes) and returns the comparison. The case is never
modified and the scenario is never stored.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.evidence_gap import _to_response as gap_to_response
from app.api.scoring import get_risk_model
from app.db.session import get_db
from app.decision.config import DecisionConfig, get_decision_config
from app.evidence_intel import versions as v
from app.ml.model import RiskModel
from app.schemas.scenario import (
    EvidenceScenarioRequest,
    EvidenceScenarioResponse,
    ScenarioDecision,
    ScenarioDelta,
    ScenarioScore,
    ScenarioSideResponse,
)
from app.services.scenario_service import (
    DISCLAIMER,
    EvidenceScenarioResult,
    ScenarioSide,
    UnknownEvidenceTypeError,
    run_evidence_scenario,
)
from app.services.scoring_service import CaseNotFoundError

router = APIRouter(tags=["scenario-analysis"])


def _side(case_id: str, side: ScenarioSide) -> ScenarioSideResponse:
    return ScenarioSideResponse(
        score=ScenarioScore(
            raw_probability=side.score["raw_probability"],
            calibrated_probability=side.score["calibrated_probability"],
            risk_band=side.score["risk_band"],
            top_positive_factors=side.score["top_positive_factors"],
            top_negative_factors=side.score["top_negative_factors"],
            evidence_summary=side.score["evidence_summary"],
        ),
        decision=ScenarioDecision(
            decision=side.decision["decision"],
            reason=side.decision["reason"],
            evidence_gap_downgrade=side.decision["evidence_gap_downgrade"],
            expected_recovery=side.decision["expected_recovery"],
            expected_net_value=side.decision["expected_net_value"],
            contest_cost=side.decision["contest_cost"],
            break_even_probability=side.decision["break_even_probability"],
            sensitivity=side.decision["sensitivity"],
        ),
        evidence_gap=gap_to_response(case_id, side.gap),
    )


def _critical_missing(side: ScenarioSide) -> set[str]:
    return {item.evidence_type for item in side.gap.missing_critical}


def _to_response(result: EvidenceScenarioResult) -> EvidenceScenarioResponse:
    current_critical = _critical_missing(result.current)
    scenario_critical = _critical_missing(result.scenario)

    return EvidenceScenarioResponse(
        case_id=result.case_id,
        reason_code=result.reason_code,
        evidence_added=result.evidence_added,
        evidence_removed=result.evidence_removed,
        current=_side(result.case_id, result.current),
        scenario=_side(result.case_id, result.scenario),
        delta=ScenarioDelta(
            calibrated_probability=result.probability_delta,
            expected_net_value=result.expected_net_value_delta,
            decision_changed=result.decision_changed,
            decision_from=result.current.decision["decision"],
            decision_to=result.scenario.decision["decision"],
            critical_gaps_resolved=sorted(current_critical - scenario_critical),
            critical_gaps_introduced=sorted(scenario_critical - current_critical),
        ),
        model_version=result.current.score["model_version"],
        feature_schema_version=result.current.score["feature_schema_version"],
        decision_policy_version=result.current.decision["decision_policy_version"],
        evidence_schema_version=v.EVIDENCE_SCHEMA_VERSION,
        generated_at=result.generated_at,
        persisted=False,
        disclaimer=DISCLAIMER,
    )


@router.post("/cases/{case_id}/evidence-scenario", response_model=EvidenceScenarioResponse)
def evidence_scenario(
    case_id: str,
    request: EvidenceScenarioRequest,
    db: Session = Depends(get_db),
    model: RiskModel = Depends(get_risk_model),
    decision_config: DecisionConfig = Depends(get_decision_config),
) -> EvidenceScenarioResponse:
    """"What if this evidence were added or removed?" for a real case.

    Both sides are evaluated with the same feature builder, the same risk-v1
    model and the same decision-v1 policy -- the only difference is the
    evidence list. The comparison is scenario analysis, NOT a causal
    estimate of what obtaining the evidence would do (see `disclaimer`).

    The stored case is never modified and the scenario is never persisted.
    """
    try:
        result = run_evidence_scenario(
            db,
            case_id,
            add=request.add_evidence,
            remove=request.remove_evidence,
            risk_model=model,
            decision_config=decision_config,
        )
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except UnknownEvidenceTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return _to_response(result)
