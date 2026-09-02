from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.scoring import get_risk_model
from app.db.session import get_db
from app.decision.config import DecisionConfig, get_decision_config
from app.decision.engine import InvalidCaseInputError
from app.ml.model import RiskModel
from app.schemas.decision import DecisionResponse
from app.services.decision_service import CaseNotFoundError, decide_case

router = APIRouter(tags=["decisions"])


@router.post("/cases/{case_id}/decision", response_model=DecisionResponse)
def decide_case_endpoint(
    case_id: str,
    top_n: int = Query(default=5, ge=1, le=20, description="number of SHAP factors per direction"),
    db: Session = Depends(get_db),
    model: RiskModel = Depends(get_risk_model),
    config: DecisionConfig = Depends(get_decision_config),
) -> DecisionResponse:
    """Cost-sensitive contest/no-contest recommendation for a stored dispute.

    Combines the Phase 2 calibrated winnability probability with a
    transparent expected-value model (recoverable amount, contest cost,
    expected net value, break-even probability) to recommend CONTEST,
    HUMAN_REVIEW, or DO_NOT_CONTEST. This is decision SUPPORT only: no
    dispute is ever submitted, contested, or otherwise acted upon
    automatically -- see the response's `disclaimer` field.
    """
    try:
        payload = decide_case(db, case_id, model, config, top_n=top_n)
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except InvalidCaseInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return DecisionResponse(**payload)
