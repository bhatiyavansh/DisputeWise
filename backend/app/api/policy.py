"""Phase 7B -- POST /policy/simulate, GET /policy/default.

A UI around the EXISTING decision engine. It never mutates decision-v1: the
production DecisionConfig is read-only here, and the hypothetical policy is a
separate throwaway instance handed to the same batch evaluation functions the
offline evaluation scripts use.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.scoring import get_risk_model
from app.decision.config import get_decision_config
from app.decision.schema import DECISION_POLICY_VERSION
from app.ml.model import RiskModel
from app.services.policy_service import (
    ECONOMICS_EXPLANATION,
    TUNABLE_FIELDS,
    compare_policies,
)

router = APIRouter(tags=["policy-playground"], prefix="/policy")

PROTOTYPE_NOTE = (
    "Policy simulation on the validation split -- a hypothetical routing exercise, not production "
    "policy. contest_cost and recovery_rate are PROTOTYPE ASSUMPTIONS, not verified production "
    "economics. Realized figures are a retrospective evaluation against known historical outcomes, "
    "not a guarantee of future recovery."
)


class PolicySimulationRequest(BaseModel):
    """Only the six tunable economic parameters. Every other part of
    decision-v1 -- notably the evidence gate -- is fixed."""

    model_config = ConfigDict(extra="forbid")

    contest_cost: float | None = Field(default=None, ge=0)
    recovery_rate: float | None = Field(default=None, ge=0, le=1)
    high_confidence_probability: float | None = Field(default=None, ge=0, le=1)
    low_confidence_probability: float | None = Field(default=None, ge=0, le=1)
    min_expected_net_value: float | None = None
    review_margin: float | None = Field(default=None, ge=0)


class PolicyDefaultsResponse(BaseModel):
    decision_policy_version: str
    tunable_fields: list[str]
    defaults: dict[str, float]
    economics_explanation: str
    note: str


class PolicySimulationResponse(BaseModel):
    split: str
    n_cases: int
    is_simulation: bool = True
    decision_policy_version: str
    model_version: str
    feature_schema_version: str
    default_config: dict[str, float]
    scenario_config: dict[str, float]
    changed_fields: list[str]
    default_policy: dict
    scenario_policy: dict
    contest_everything_baseline: dict
    economics_explanation: str
    note: str


@router.get("/default", response_model=PolicyDefaultsResponse)
def policy_defaults() -> PolicyDefaultsResponse:
    """The production decision-v1 parameters -- the playground's reset point."""
    config = get_decision_config()
    return PolicyDefaultsResponse(
        decision_policy_version=DECISION_POLICY_VERSION,
        tunable_fields=list(TUNABLE_FIELDS),
        defaults={field: getattr(config, field) for field in TUNABLE_FIELDS},
        economics_explanation=ECONOMICS_EXPLANATION,
        note=PROTOTYPE_NOTE,
    )


@router.post("/simulate", response_model=PolicySimulationResponse)
def simulate_policy(
    request: PolicySimulationRequest,
    model: RiskModel = Depends(get_risk_model),
) -> PolicySimulationResponse:
    """Re-route the portfolio under a hypothetical policy.

    Returns three routings of the same scored cases: production decision-v1,
    the requested hypothetical policy, and a contest-everything baseline.
    The stored decision-v1 configuration is not modified.

    Realized figures come from known historical outcomes on the validation
    split (retrospective evaluation). The locked test set is never used here
    -- moving thresholds while watching held-out outcomes would be tuning
    against the benchmark.
    """
    try:
        comparison = compare_policies(request.model_dump(exclude_none=True), risk_model=model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return PolicySimulationResponse(
        split=comparison.split,
        n_cases=comparison.n_cases,
        decision_policy_version=comparison.decision_policy_version,
        model_version=comparison.model_version,
        feature_schema_version=comparison.feature_schema_version,
        default_config=comparison.default_config,
        scenario_config=comparison.scenario_config,
        changed_fields=comparison.changed_fields,
        default_policy=comparison.default_policy,
        scenario_policy=comparison.scenario_policy,
        contest_everything_baseline=comparison.contest_everything_baseline,
        economics_explanation=ECONOMICS_EXPLANATION,
        note=PROTOTYPE_NOTE,
    )
