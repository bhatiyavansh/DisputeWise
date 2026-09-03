"""Score a single stored case with the Phase 2 winnability model.

Bridges the relational schema to the ML feature builder: it reconstructs the
exact frame shapes `app.ml.features.build_features` expects (keyed by the
string business identifiers, not the integer surrogate keys), so the API and
the offline training/evaluation pipeline share one featurization code path.

Notably, the outcomes table is never loaded here -- at scoring time the label
does not exist, which is precisely the situation the feature builder's
signature already enforces.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.ml import schema
from app.ml.features import build_features
from app.ml.model import RiskModel
from app.models.dispute import Dispute
from app.models.evidence import Evidence
from app.models.transaction import Transaction


class CaseNotFoundError(LookupError):
    pass


def _load_case(db: Session, case_id: str) -> tuple[Dispute, list[Evidence]]:
    dispute = db.execute(
        select(Dispute)
        .options(joinedload(Dispute.transaction).joinedload(Transaction.customer))
        .where(Dispute.dispute_id == case_id)
    ).unique().scalar_one_or_none()

    if dispute is None:
        raise CaseNotFoundError(case_id)

    evidence = list(
        db.execute(
            select(Evidence).where(Evidence.dispute_id == dispute.id).order_by(Evidence.evidence_type)
        ).scalars().all()
    )
    return dispute, evidence


def _to_frames(dispute: Dispute, evidence_rows: list[Evidence]) -> dict[str, pd.DataFrame]:
    transaction = dispute.transaction
    customer = transaction.customer

    disputes = pd.DataFrame(
        [
            {
                "dispute_id": dispute.dispute_id,
                "transaction_id": transaction.transaction_id,
                "reason_code": dispute.reason_code,
                "dispute_amount": float(dispute.dispute_amount),
                "created_at": dispute.created_at,
                "response_deadline": dispute.response_deadline,
            }
        ]
    )

    transactions = pd.DataFrame(
        [
            {
                "transaction_id": transaction.transaction_id,
                "customer_id": customer.customer_id,
                "amount": float(transaction.amount),
                "payment_method": transaction.payment_method,
                "created_at": transaction.created_at,
                "captured_at": transaction.captured_at,
                "status": transaction.status,
                "billing_address_id": transaction.billing_address_id,
                "shipping_address_id": transaction.shipping_address_id,
                "avs_result": transaction.avs_result,
                "cvv_result": transaction.cvv_result,
                "three_ds_authenticated": transaction.three_ds_authenticated,
            }
        ]
    )

    customers = pd.DataFrame(
        [
            {
                "customer_id": customer.customer_id,
                "account_age_days": customer.account_age_days,
                "previous_order_count": customer.previous_order_count,
                "previous_successful_order_count": customer.previous_successful_order_count,
                "previous_dispute_count": customer.previous_dispute_count,
                "previous_refund_count": customer.previous_refund_count,
            }
        ]
    )

    evidence = pd.DataFrame(
        [
            {
                "dispute_id": dispute.dispute_id,
                "evidence_type": row.evidence_type,
                "available": row.available,
                "value": row.value,
                "relevance": row.relevance,
                "strength": row.strength,
            }
            for row in evidence_rows
        ],
        columns=["dispute_id", "evidence_type", "available", "value", "relevance", "strength"],
    )

    return {
        "disputes": disputes,
        "transactions": transactions,
        "customers": customers,
        "evidence": evidence,
    }


def _evidence_summary(evidence_rows: list[Evidence]) -> dict:
    available_types = {row.evidence_type for row in evidence_rows if row.available}
    high_relevance_types = {row.evidence_type for row in evidence_rows if row.relevance == "high"}
    strong = sum(
        1
        for row in evidence_rows
        if row.available and (row.strength or 0.0) >= schema.STRONG_EVIDENCE_STRENGTH_THRESHOLD
    )
    return {
        "total": len(evidence_rows),
        "available": len(available_types),
        "strong": strong,
        "high_relevance_total": len(high_relevance_types),
        "high_relevance_available": len(high_relevance_types & available_types),
        "missing_key_types": sorted(high_relevance_types - available_types),
    }


def score_parts(dispute, evidence_rows: list, model: RiskModel, top_n: int = 5) -> dict:
    """Score from already-materialized case parts, with no database access.

    This is the entire Phase 2 scoring path -- frame construction, the
    leakage-safe feature builder, the model, and calibration -- factored out
    of score_case() so callers that hold case parts in memory rather than in
    the database (Phase 6 simulation) run *exactly* this code rather than a
    parallel implementation of it.

    `dispute` and `evidence_rows` are duck-typed: any object exposing the
    same attributes as app.models.dispute.Dispute (including .transaction ->
    .customer) and app.models.evidence.Evidence works. Nothing here reads
    the outcomes table -- the leakage guarantee in build_features()'s
    signature is inherited unchanged.
    """
    frames = _to_frames(dispute, evidence_rows)

    features = build_features(
        frames["disputes"], frames["transactions"], frames["customers"], frames["evidence"]
    )
    scored = model.score_cases(features, top_n=top_n)[0]

    return {
        "case_id": dispute.dispute_id,
        "model_version": model.model_version,
        "feature_schema_version": model.feature_schema_version,
        "reason_code": dispute.reason_code,
        "raw_probability": round(scored.raw_probability, 6),
        "calibrated_probability": round(scored.calibrated_probability, 6),
        "risk_band": scored.risk_band,
        "calibration_method": model.calibration_method,
        "top_positive_factors": scored.top_positive_factors,
        "top_negative_factors": scored.top_negative_factors,
        "evidence_summary": _evidence_summary(evidence_rows),
    }


def score_case(db: Session, case_id: str, model: RiskModel, top_n: int = 5) -> dict:
    """Score one stored case. Raises CaseNotFoundError if it does not exist."""
    dispute, evidence_rows = _load_case(db, case_id)
    return score_parts(dispute, evidence_rows, model, top_n=top_n)
