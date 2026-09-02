"""Cost-sensitive decisioning for a single stored case.

Reuses Phase 2's scoring service for the calibrated probability, evidence
summary, and SHAP factors -- this module does not reimplement scoring, and
does not touch app/ml/ or app/services/scoring_service.py. It adds exactly
one more piece of data scoring doesn't need: the dispute's monetary amount.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.decision.config import DecisionConfig
from app.decision.policy import evaluate_case
from app.ml.model import RiskModel
from app.models.dispute import Dispute
from app.services.scoring_service import CaseNotFoundError, score_case

__all__ = ["CaseNotFoundError", "decide_case"]


def _load_dispute_amount(db: Session, case_id: str) -> float:
    amount = db.execute(
        select(Dispute.dispute_amount).where(Dispute.dispute_id == case_id)
    ).scalar_one_or_none()
    if amount is None:
        raise CaseNotFoundError(case_id)
    return float(amount)


def decide_case(db: Session, case_id: str, model: RiskModel, config: DecisionConfig, top_n: int = 5) -> dict:
    """Score + economically evaluate one stored case.

    Raises CaseNotFoundError if the case does not exist (propagated straight
    from score_case, which performs the primary existence check).
    """
    score_payload = score_case(db, case_id, model, top_n=top_n)
    dispute_amount = _load_dispute_amount(db, case_id)

    evidence_summary = score_payload["evidence_summary"]
    missing_high_relevance_evidence: list[str] = list(evidence_summary["missing_key_types"])

    decision_payload = evaluate_case(
        calibrated_probability=score_payload["calibrated_probability"],
        dispute_amount=dispute_amount,
        missing_high_relevance_evidence=missing_high_relevance_evidence,
        config=config,
    )

    return {
        "case_id": score_payload["case_id"],
        "model_version": score_payload["model_version"],
        "feature_schema_version": score_payload["feature_schema_version"],
        "reason_code": score_payload["reason_code"],
        "risk_band": score_payload["risk_band"],
        "top_positive_factors": score_payload["top_positive_factors"],
        "top_negative_factors": score_payload["top_negative_factors"],
        "evidence_summary": evidence_summary,
        **decision_payload,
    }
