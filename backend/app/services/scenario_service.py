"""Phase 7A -- evidence scenario analysis on a real case.

    "What happens to this dispute if this evidence is added or removed?"

Scores the case as it stands and again with hypothetical evidence changes,
using the same feature builder, the same risk-v1 model, the same decision-v1
policy and the same evidence-v1 gap analyzer for both sides. There is no
separate scenario probability logic -- the only difference between the two
runs is the evidence list handed to score_parts().

THIS IS NOT CAUSAL INFERENCE. The two numbers are two model evaluations
under two different feature vectors. They do not estimate the effect of
obtaining the evidence in the real world (which would also change who the
merchant is, which cases they file, and what actually happened). The API
response says so, and the UI repeats it.

Nothing is persisted: the scenario evidence list is a detached copy (see
scenario_builder), and the ORM rows loaded here are only read.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.decision.config import DecisionConfig
from app.decision.policy import evaluate_case
from app.evidence_intel.gap_analyzer import EvidenceGapResult, analyze_gap, case_evidence_state_from_rows
from app.ml.model import RiskModel
from app.services.scoring_service import _load_case, score_parts
from app.simulation.scenario_builder import UnknownEvidenceTypeError, apply_evidence_changes

__all__ = ["UnknownEvidenceTypeError", "ScenarioSide", "EvidenceScenarioResult", "run_evidence_scenario"]

DISCLAIMER = (
    "Scenario analysis -- not a causal estimate. These are two model evaluations under two "
    "different evidence states, not a prediction of what obtaining this evidence would cause. "
    "Nothing was saved and the case is unchanged."
)


class ScenarioSide:
    """One side of the comparison (current or hypothetical)."""

    def __init__(self, *, score: dict, decision: dict, gap: EvidenceGapResult) -> None:
        self.score = score
        self.decision = decision
        self.gap = gap


class EvidenceScenarioResult:
    def __init__(
        self,
        *,
        case_id: str,
        reason_code: str,
        current: ScenarioSide,
        scenario: ScenarioSide,
        evidence_added: list[str],
        evidence_removed: list[str],
        generated_at: str,
    ) -> None:
        self.case_id = case_id
        self.reason_code = reason_code
        self.current = current
        self.scenario = scenario
        self.evidence_added = evidence_added
        self.evidence_removed = evidence_removed
        self.generated_at = generated_at

    @property
    def probability_delta(self) -> float:
        return round(
            self.scenario.score["calibrated_probability"] - self.current.score["calibrated_probability"], 6
        )

    @property
    def expected_net_value_delta(self) -> float:
        return round(
            self.scenario.decision["expected_net_value"] - self.current.decision["expected_net_value"], 2
        )

    @property
    def decision_changed(self) -> bool:
        return self.scenario.decision["decision"] != self.current.decision["decision"]


def _evaluate(dispute, evidence_rows, *, risk_model: RiskModel, decision_config: DecisionConfig) -> ScenarioSide:
    """One full evaluation of a case state. Identical code path for both sides."""
    score = score_parts(dispute, evidence_rows, risk_model)
    decision = evaluate_case(
        calibrated_probability=score["calibrated_probability"],
        dispute_amount=float(dispute.dispute_amount),
        missing_high_relevance_evidence=list(score["evidence_summary"]["missing_key_types"]),
        config=decision_config,
    )
    gap = analyze_gap(dispute.reason_code, case_evidence_state_from_rows(evidence_rows))
    return ScenarioSide(score=score, decision=decision, gap=gap)


def run_evidence_scenario(
    db: Session,
    case_id: str,
    *,
    add: list[str],
    remove: list[str],
    risk_model: RiskModel,
    decision_config: DecisionConfig,
) -> EvidenceScenarioResult:
    """Score a stored case as-is and under hypothetical evidence changes.

    Raises CaseNotFoundError if the case does not exist, and
    UnknownEvidenceTypeError for an evidence type outside the taxonomy.
    """
    dispute, evidence_rows = _load_case(db, case_id)

    # Built first so an invalid evidence type fails before any scoring work.
    scenario_evidence = apply_evidence_changes(dispute, evidence_rows, add=add, remove=remove)

    current = _evaluate(dispute, evidence_rows, risk_model=risk_model, decision_config=decision_config)
    scenario = _evaluate(dispute, scenario_evidence, risk_model=risk_model, decision_config=decision_config)

    return EvidenceScenarioResult(
        case_id=dispute.dispute_id,
        reason_code=dispute.reason_code,
        current=current,
        scenario=scenario,
        evidence_added=sorted(add),
        evidence_removed=sorted(remove),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
