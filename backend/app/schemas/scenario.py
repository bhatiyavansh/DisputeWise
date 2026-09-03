"""Phase 7A -- POST /cases/{id}/evidence-scenario schemas.

The request carries only evidence changes. Like SimulationRequest it is
`extra="forbid"`, so no outcome/target field (or any other unknown key) can
enter -- and there is no field here that describes a dispute's result.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ml import schema as ml_schema
from app.schemas.decision import SensitivityPoint
from app.schemas.evidence_intel import EvidenceGapResponse
from app.schemas.scoring import ContributingFactor, EvidenceSummary

_TARGET_FIELDS = frozenset(ml_schema.FORBIDDEN_COLUMNS)


class EvidenceScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    add_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence types to treat as hypothetically available (corroborating).",
    )
    remove_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence types to treat as hypothetically not on file.",
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_target_fields(cls, data):
        if isinstance(data, dict):
            leaked = sorted(_TARGET_FIELDS & set(data))
            if leaked:
                raise ValueError(
                    f"outcome/target fields are never accepted by scenario analysis: {leaked}."
                )
        return data

    @field_validator("add_evidence", "remove_evidence")
    @classmethod
    def _known_evidence_types(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(ml_schema.ALL_EVIDENCE_TYPES))
        if unknown:
            raise ValueError(
                f"unknown evidence types: {unknown}. Valid types: {sorted(ml_schema.ALL_EVIDENCE_TYPES)}"
            )
        return value

    @model_validator(mode="after")
    def _at_least_one_change_and_no_conflict(self) -> EvidenceScenarioRequest:
        conflict = set(self.add_evidence) & set(self.remove_evidence)
        if conflict:
            raise ValueError(f"evidence types listed as both added and removed: {sorted(conflict)}")
        if not self.add_evidence and not self.remove_evidence:
            raise ValueError("a scenario must change at least one evidence type")
        return self


class ScenarioScore(BaseModel):
    raw_probability: float
    calibrated_probability: float
    risk_band: str
    top_positive_factors: list[ContributingFactor]
    top_negative_factors: list[ContributingFactor]
    evidence_summary: EvidenceSummary


class ScenarioDecision(BaseModel):
    decision: str
    reason: str
    evidence_gap_downgrade: bool
    expected_recovery: float
    expected_net_value: float
    contest_cost: float
    break_even_probability: float | None
    sensitivity: list[SensitivityPoint]


class ScenarioSideResponse(BaseModel):
    score: ScenarioScore
    decision: ScenarioDecision
    evidence_gap: EvidenceGapResponse


class ScenarioDelta(BaseModel):
    calibrated_probability: float
    expected_net_value: float
    decision_changed: bool
    decision_from: str
    decision_to: str
    critical_gaps_resolved: list[str]
    critical_gaps_introduced: list[str]


class EvidenceScenarioResponse(BaseModel):
    case_id: str
    reason_code: str
    is_scenario: bool = True
    evidence_added: list[str]
    evidence_removed: list[str]
    current: ScenarioSideResponse
    scenario: ScenarioSideResponse
    delta: ScenarioDelta

    model_version: str
    feature_schema_version: str
    decision_policy_version: str
    evidence_schema_version: str
    generated_at: str
    persisted: bool = Field(
        default=False, description="Always false: scenario analysis never modifies or stores the case."
    )
    disclaimer: str
