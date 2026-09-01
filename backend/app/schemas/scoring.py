from pydantic import BaseModel, Field


class ContributingFactor(BaseModel):
    """One SHAP-attributed driver of the prediction.

    `contribution` is in the model's raw margin (log-odds) space, so it is a
    relative driver, not an additive percentage-point change in probability.
    """

    feature: str
    contribution: float
    value: float | int | bool | None = None
    description: str


class EvidenceSummary(BaseModel):
    total: int = Field(description="evidence records on file for this case")
    available: int = Field(description="records whose evidence is actually present")
    strong: int = Field(description="available records with strength >= 0.6")
    high_relevance_total: int = Field(description="evidence types highly relevant to this reason code")
    high_relevance_available: int
    missing_key_types: list[str] = Field(
        description="high-relevance evidence types with no available record for this case"
    )


class ScoreResponse(BaseModel):
    case_id: str
    model_version: str
    feature_schema_version: str
    reason_code: str
    raw_probability: float = Field(description="uncalibrated LightGBM output")
    calibrated_probability: float = Field(description="P(favorable outcome | evidence), calibrated")
    risk_band: str = Field(description="HIGH_WINNABILITY | MEDIUM_WINNABILITY | LOW_WINNABILITY")
    calibration_method: str
    top_positive_factors: list[ContributingFactor]
    top_negative_factors: list[ContributingFactor]
    evidence_summary: EvidenceSummary
    disclaimer: str = Field(
        default=(
            "Winnability probability only. This is decision SUPPORT, not a recommendation to "
            "contest: expected recovery vs. contest cost is not modelled in this phase, and no "
            "dispute is ever submitted automatically."
        )
    )
