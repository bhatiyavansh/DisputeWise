"""Phase 6 -- POST /simulate request/response schemas.

LEAKAGE POLICY
--------------
The request model is `extra="forbid"`, so any field that is not explicitly
declared below is rejected with a 422 rather than silently ignored. Every
target/outcome/post-dispute field named in app/ml/schema.py's
FORBIDDEN_COLUMNS is therefore unreachable by construction -- there is no
`favorable_outcome`, `recovery_amount`, `outcome_at`, `outcome_source`, or
any other post-decision field anywhere in this model, and one cannot be
smuggled in as an extra key.

`_TARGET_FIELDS` below additionally turns the generic "extra inputs are not
permitted" 422 into an explicit, named refusal for the specific fields that
would constitute leakage, so a caller attempting it gets told exactly why.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ml import schema as ml_schema
from app.schemas.decision import SensitivityPoint
from app.schemas.evidence_intel import (
    ClaimVerificationResponse,
    EvidenceGapResponse,
    GeneratedClaimResponse,
    RetrievalResultResponse,
)
from app.schemas.scoring import ContributingFactor, EvidenceSummary

ReasonCode = Literal["unauthorized_transaction", "goods_not_received", "duplicate_charge"]
PaymentMethod = Literal["card", "upi", "netbanking"]
TransactionStatus = Literal["captured", "refunded", "failed"]
DisputeStatus = Literal["open", "evidence_submitted", "under_review", "closed"]

# Named purely to produce a precise error message; `extra="forbid"` already
# makes all of them unreachable.
_TARGET_FIELDS = frozenset(ml_schema.FORBIDDEN_COLUMNS)


class SimulationRequest(BaseModel):
    """A hypothetical dispute, described in facts available at decision time.

    Every field here is something a merchant could know *before* the dispute
    is resolved. Nothing describes the outcome.
    """

    model_config = ConfigDict(extra="forbid")

    simulation_case_id: str = Field(
        default="SIM-CASE",
        max_length=32,
        description="Label for this scenario. Never written to the database; not a real case ID.",
    )

    # --- dispute -----------------------------------------------------------
    reason_code: ReasonCode
    dispute_amount: float = Field(gt=0, le=10_000_000)
    dispute_status: DisputeStatus = "open"

    # --- transaction -------------------------------------------------------
    transaction_amount: float = Field(gt=0, le=10_000_000)
    payment_method: PaymentMethod = "card"
    transaction_status: TransactionStatus = "captured"
    capture_lag_minutes: int = Field(default=30, ge=0, le=100_000)
    days_transaction_to_dispute: int = Field(default=30, ge=0, le=3_650)
    days_to_respond: int = Field(default=14, ge=0, le=365)

    # --- authentication ----------------------------------------------------
    three_ds_authenticated: bool = False
    avs_result: Literal["Y", "N", "U", "M"] = "N"
    cvv_result: Literal["M", "N", "U"] = "N"
    device_match: bool = False
    ip_match: bool = False
    billing_shipping_match: bool = True

    # --- customer (as-of account state, never aggregated from other cases) --
    account_age_days: int = Field(default=180, ge=0, le=36_500)
    previous_order_count: int = Field(default=0, ge=0, le=100_000)
    previous_successful_order_count: int = Field(default=0, ge=0, le=100_000)
    previous_dispute_count: int = Field(default=0, ge=0, le=100_000)
    previous_refund_count: int = Field(default=0, ge=0, le=100_000)

    # --- fulfillment -------------------------------------------------------
    delivery_confirmed: bool = False
    tracking_available: bool = False
    delivery_address_match: bool = False
    proof_of_delivery: bool = False
    delivery_days_after_capture: int = Field(default=3, ge=0, le=365)

    # --- communication -----------------------------------------------------
    customer_communication_available: bool = False
    cancellation_request: bool = False
    refund_request: bool = False

    # --- explicit evidence-on-file overrides -------------------------------
    evidence_on_file: list[str] = Field(
        default_factory=list,
        description="Force these evidence types to be on file, overriding the default derived from the facts above.",
    )
    evidence_not_on_file: list[str] = Field(
        default_factory=list,
        description="Force these evidence types to be absent, overriding the default derived from the facts above.",
    )

    # --- generation --------------------------------------------------------
    generate_response: bool = Field(
        default=False,
        description="Run LLM generation + claim verification. Off by default: it is the only slow, non-deterministic stage.",
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_target_fields(cls, data):
        """Refuse outcome/target fields by name, before generic validation.

        `extra="forbid"` already rejects them; this exists so the refusal is
        explicit and auditable rather than a generic "extra inputs are not
        permitted", and so the leakage boundary is visible in the code.
        """
        if isinstance(data, dict):
            leaked = sorted(_TARGET_FIELDS & set(data))
            if leaked:
                raise ValueError(
                    f"outcome/target fields are never accepted by simulation: {leaked}. "
                    "Simulation scores a hypothetical dispute using only information available "
                    "at decision time."
                )
        return data

    @field_validator("previous_successful_order_count")
    @classmethod
    def _successful_orders_within_total(cls, value: int, info) -> int:
        total = info.data.get("previous_order_count")
        if total is not None and value > total:
            raise ValueError("previous_successful_order_count cannot exceed previous_order_count")
        return value

    @field_validator("evidence_on_file", "evidence_not_on_file")
    @classmethod
    def _known_evidence_types(cls, value: list[str]) -> list[str]:
        """Validated against the single source of truth for the taxonomy
        (app/ml/schema.py) rather than a re-typed Literal that could drift."""
        unknown = sorted(set(value) - set(ml_schema.ALL_EVIDENCE_TYPES))
        if unknown:
            raise ValueError(
                f"unknown evidence types: {unknown}. Valid types: {sorted(ml_schema.ALL_EVIDENCE_TYPES)}"
            )
        return value

    @model_validator(mode="after")
    def _no_conflicting_evidence_overrides(self) -> SimulationRequest:
        conflict = set(self.evidence_on_file) & set(self.evidence_not_on_file)
        if conflict:
            raise ValueError(
                f"evidence types listed as both on-file and not-on-file: {sorted(conflict)}"
            )
        return self


class SimulationScoreResponse(BaseModel):
    raw_probability: float
    calibrated_probability: float
    risk_band: str
    calibration_method: str
    top_positive_factors: list[ContributingFactor]
    top_negative_factors: list[ContributingFactor]
    evidence_summary: EvidenceSummary


class SimulationDecisionResponse(BaseModel):
    decision: str
    reason: str
    decision_policy_version: str
    evidence_gap_downgrade: bool
    dispute_amount: float
    recovery_rate: float
    recoverable_amount: float
    contest_cost: float
    expected_recovery: float
    expected_net_value: float
    break_even_probability: float | None
    break_even_explanation: str
    sensitivity: list[SensitivityPoint]


class SimulationGenerationResponse(BaseModel):
    response_state: str
    response_state_reason: str
    generation_available: bool
    summary: str | None
    response_body: str | None
    claims: list[GeneratedClaimResponse]
    claim_verifications: list[ClaimVerificationResponse]
    missing_evidence: list[str]


class SimulationTraceResponse(BaseModel):
    simulation_id: str
    model_version: str
    feature_schema_version: str
    decision_policy_version: str
    evidence_schema_version: str
    knowledge_base_version: str
    retrieval_config_version: str
    prompt_version: str | None
    response_schema_version: str | None
    verifier_version: str | None
    retrieved_source_ids: list[str]
    retrieved_chunk_ids: list[str]
    generated_at: str
    persisted: bool = Field(
        default=False,
        description="Always false: simulations are scenario analysis and are never written to the database.",
    )


class SimulationResponse(BaseModel):
    simulation_id: str
    is_simulation: bool = True
    reason_code: str
    score: SimulationScoreResponse
    decision: SimulationDecisionResponse
    evidence_gap: EvidenceGapResponse
    retrieved_sources: list[RetrievalResultResponse]
    generation: SimulationGenerationResponse | None
    trace: SimulationTraceResponse
    disclaimer: str
