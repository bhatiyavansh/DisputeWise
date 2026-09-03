"""Phase 6 -- run a hypothetical dispute through the existing pipeline.

    request -> simulation case -> [Phase 2 scoring] -> [Phase 3 decision]
            -> [Phase 4 gap -> packet -> retrieval -> generation -> verifier]

Every stage below is a call into the module that already owns it. This
service contains no feature engineering, no probability math, no decision
thresholds, and no verification rules of its own -- if a number appears in
the response, some frozen Phase 2/3/4 module produced it.

NO PERSISTENCE. This module imports no ORM model and takes no Session. A
simulation cannot write to the database because it has nothing to write
with -- the guarantee is structural, not a convention.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.decision.config import DecisionConfig
from app.decision.policy import evaluate_case
from app.evidence_intel import versions as v
from app.evidence_intel.gap_analyzer import EvidenceGapResult, analyze_gap, case_evidence_state_from_rows
from app.evidence_intel.generation import GeneratedDraft, LLMOutputError, generate_draft
from app.evidence_intel.llm_provider import LLMProvider
from app.evidence_intel.packet import EvidencePacket, build_packet
from app.evidence_intel.reference_data import load_reference_data
from app.evidence_intel.retrieval import RetrievalResult, retrieve_for_case
from app.evidence_intel.safety import determine_response_state
from app.evidence_intel.verifier import ClaimVerification, verify_claims, verify_response_body
from app.ml.model import RiskModel
from app.services.scoring_service import score_parts
from app.simulation.case_builder import SimulationCase, build_simulation_case


class SimulationResult:
    """Everything POST /simulate returns, assembled in one place."""

    def __init__(
        self,
        *,
        simulation_id: str,
        reason_code: str,
        score: dict,
        decision: dict,
        gap: EvidenceGapResult,
        packet: EvidencePacket,
        retrieval_results: list[RetrievalResult],
        generation_ran: bool,
        generation_available: bool,
        draft: GeneratedDraft | None,
        verifications: list[ClaimVerification],
        response_state: str | None,
        response_state_reason: str | None,
        generated_at: str,
    ) -> None:
        self.simulation_id = simulation_id
        self.reason_code = reason_code
        self.score = score
        self.decision = decision
        self.gap = gap
        self.packet = packet
        self.retrieval_results = retrieval_results
        self.generation_ran = generation_ran
        self.generation_available = generation_available
        self.draft = draft
        self.verifications = verifications
        self.response_state = response_state
        self.response_state_reason = response_state_reason
        self.generated_at = generated_at


def _run_generation(
    packet: EvidencePacket,
    retrieval_results: list[RetrievalResult],
    llm_provider: LLMProvider | None,
) -> tuple[bool, GeneratedDraft | None, list[ClaimVerification], str, str]:
    """Generation + verification, with the same states and the same safe
    failure behavior as the stored-case path in evidence_intel_service."""
    if llm_provider is None:
        return (
            False,
            None,
            [],
            v.GENERATION_UNAVAILABLE,
            "No LLM provider is configured. Scoring, decision, evidence gap and retrieval above are fully available; "
            "response generation is not.",
        )

    try:
        draft = generate_draft(packet, retrieval_results, llm_provider)
    except LLMOutputError as exc:
        return (True, None, [], v.DRAFT_BLOCKED, f"Generation failed: {exc}")

    verifications = verify_claims(draft.claims, packet, retrieval_results)
    verifications = verifications + [verify_response_body(draft.response_body)]
    response_state, reason = determine_response_state(verifications)
    return (True, draft, verifications, response_state, reason)


def run_simulation(
    spec,
    *,
    risk_model: RiskModel,
    decision_config: DecisionConfig,
    llm_provider: LLMProvider | None = None,
) -> SimulationResult:
    """Run one hypothetical dispute through the full pipeline. No DB access.

    `spec` is a validated SimulationRequest.
    """
    reference = load_reference_data()
    case: SimulationCase = build_simulation_case(spec, reference=reference)
    dispute = case.dispute

    # --- Phase 2: the exact scoring path stored cases use ------------------
    score = score_parts(dispute, case.evidence, risk_model)

    # --- Phase 3: the exact decision policy stored cases use ---------------
    decision = evaluate_case(
        calibrated_probability=score["calibrated_probability"],
        dispute_amount=float(dispute.dispute_amount),
        missing_high_relevance_evidence=list(score["evidence_summary"]["missing_key_types"]),
        config=decision_config,
    )

    # --- Phase 4: gap -> packet -> retrieval ------------------------------
    gap = analyze_gap(dispute.reason_code, case_evidence_state_from_rows(case.evidence), reference)
    packet = build_packet(
        dispute_id=dispute.dispute_id,
        reason_code=dispute.reason_code,
        dispute_amount=float(dispute.dispute_amount),
        dispute_status=dispute.status,
        created_at=dispute.created_at.isoformat(),
        payment_method=dispute.transaction.payment_method,
        transaction_status=dispute.transaction.status,
        three_ds_authenticated=dispute.transaction.three_ds_authenticated,
        avs_result=dispute.transaction.avs_result,
        cvv_result=dispute.transaction.cvv_result,
        account_age_days=dispute.transaction.customer.account_age_days,
        previous_order_count=dispute.transaction.customer.previous_order_count,
        previous_successful_order_count=dispute.transaction.customer.previous_successful_order_count,
        previous_dispute_count=dispute.transaction.customer.previous_dispute_count,
        previous_refund_count=dispute.transaction.customer.previous_refund_count,
        evidence_rows=case.evidence,
        reference=reference,
    )
    retrieval_results = retrieve_for_case(reason_code=dispute.reason_code, gap=gap)

    # --- Phase 4: generation + verification (opt-in) ----------------------
    generation_ran = bool(spec.generate_response)
    generation_available = False
    draft: GeneratedDraft | None = None
    verifications: list[ClaimVerification] = []
    response_state: str | None = None
    response_state_reason: str | None = None

    if generation_ran:
        (
            generation_available,
            draft,
            verifications,
            response_state,
            response_state_reason,
        ) = _run_generation(packet, retrieval_results, llm_provider)

    return SimulationResult(
        simulation_id=f"SIM-{uuid.uuid4().hex[:12]}",
        reason_code=dispute.reason_code,
        score=score,
        decision=decision,
        gap=gap,
        packet=packet,
        retrieval_results=retrieval_results,
        generation_ran=generation_ran,
        generation_available=generation_available,
        draft=draft,
        verifications=verifications,
        response_state=response_state,
        response_state_reason=response_state_reason,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
