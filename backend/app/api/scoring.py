from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.ml.model import ModelNotAvailableError, RiskModel, get_model
from app.schemas.scoring import ScoreResponse
from app.services.scoring_service import CaseNotFoundError, score_case

router = APIRouter(tags=["scoring"])


def get_risk_model() -> RiskModel:
    """Model dependency. 503 (not 500) when artifacts are absent: the service
    is healthy, the model just has not been trained in this environment."""
    try:
        return get_model()
    except ModelNotAvailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "Risk model artifacts are not available.",
                "remedy": "Train the model: python scripts/train_model.py",
                "error": str(exc),
            },
        ) from exc


@router.post("/cases/{case_id}/score", response_model=ScoreResponse)
def score_case_endpoint(
    case_id: str,
    top_n: int = Query(default=5, ge=1, le=20, description="number of SHAP factors per direction"),
    db: Session = Depends(get_db),
    model: RiskModel = Depends(get_risk_model),
) -> ScoreResponse:
    """Predict P(favorable outcome | evidence) for a stored dispute.

    Returns a calibrated winnability probability with SHAP-attributed drivers.
    This is decision support only -- it neither recommends contesting (that is
    Phase 3's cost-sensitive decision engine) nor takes any action.
    """
    try:
        payload = score_case(db, case_id, model, top_n=top_n)
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return ScoreResponse(**payload)
