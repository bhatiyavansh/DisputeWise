from pydantic import BaseModel, Field

from app.schemas.scoring import ContributingFactor, EvidenceSummary


class SensitivityPoint(BaseModel):
    """One point on the expected-net-value-vs-probability curve.

    Explainability surface only -- never used to change the decision.
    """

    probability: float
    delta: float = Field(description="offset from the case's actual calibrated_probability")
    expected_recovery: float
    expected_net_value: float


class DecisionResponse(BaseModel):
    case_id: str
    model_version: str
    feature_schema_version: str
    decision_policy_version: str
    reason_code: str

    decision: str = Field(description="CONTEST | HUMAN_REVIEW | DO_NOT_CONTEST")
    reason: str = Field(description="deterministic, template-generated explanation")
    evidence_gap_downgrade: bool = Field(
        description="true if a CONTEST recommendation was downgraded to HUMAN_REVIEW "
        "because high-relevance evidence for this reason code is missing"
    )

    calibrated_probability: float = Field(description="from Phase 2 /score; not recomputed here")
    risk_band: str

    dispute_amount: float
    recovery_rate: float
    recoverable_amount: float
    contest_cost: float
    expected_recovery: float
    expected_net_value: float
    break_even_probability: float | None
    break_even_explanation: str
    sensitivity: list[SensitivityPoint]

    top_positive_factors: list[ContributingFactor]
    top_negative_factors: list[ContributingFactor]
    evidence_summary: EvidenceSummary

    disclaimer: str
