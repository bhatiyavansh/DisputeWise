"""Phase 4 orchestration: loads a case, then runs the evidence-gap ->
evidence-packet -> retrieval -> (optional) generation -> verification ->
safety -> trace pipeline described in app/evidence_intel/.

Mirrors the loading pattern already established in scoring_service.py /
decision_service.py rather than modifying either (both are frozen Phase 2/3
code) -- a short, independent query here is preferable to reaching into
those modules' private helpers.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.decision.config import DecisionConfig
from app.evidence_intel import versions as v
from app.evidence_intel.gap_analyzer import EvidenceGapResult, case_evidence_state_from_rows, analyze_gap
from app.evidence_intel.generation import (
    GeneratedDraft,
    InvalidOutputError,
    LLMOutputError,
    ProviderUnavailableError,
    generate_draft,
)
from app.evidence_intel.llm_provider import LLMProvider
from app.evidence_intel.packet import EvidencePacket, build_packet
from app.evidence_intel.reference_data import load_reference_data
from app.evidence_intel.retrieval import RetrievalResult, retrieve_for_case
from app.evidence_intel.safety import determine_response_state
from app.evidence_intel.trace import ResponseTrace, build_trace
from app.evidence_intel.verifier import ClaimVerification, verify_claims, verify_response_body
from app.ml.model import RiskModel
from app.models.dispute import Dispute
from app.models.evidence import Evidence
from app.models.transaction import Transaction
from app.services.decision_service import decide_case
from app.services.scoring_service import CaseNotFoundError


def _load_case(db: Session, case_id: str) -> tuple[Dispute, list[Evidence]]:
    dispute = (
        db.execute(
            select(Dispute)
            .options(joinedload(Dispute.transaction).joinedload(Transaction.customer))
            .where(Dispute.dispute_id == case_id)
        )
        .unique()
        .scalar_one_or_none()
    )
    if dispute is None:
        raise CaseNotFoundError(case_id)

    evidence_rows = list(
        db.execute(select(Evidence).where(Evidence.dispute_id == dispute.id).order_by(Evidence.evidence_type))
        .scalars()
        .all()
    )
    return dispute, evidence_rows


def build_case_packet(db: Session, case_id: str) -> EvidencePacket:
    """Part A + B: gap analysis + evidence packet for a stored case."""
    dispute, evidence_rows = _load_case(db, case_id)
    transaction = dispute.transaction
    customer = transaction.customer
    reference = load_reference_data()

    return build_packet(
        dispute_id=dispute.dispute_id,
        reason_code=dispute.reason_code,
        dispute_amount=dispute.dispute_amount,
        dispute_status=dispute.status,
        created_at=dispute.created_at.isoformat(),
        payment_method=transaction.payment_method,
        transaction_status=transaction.status,
        three_ds_authenticated=transaction.three_ds_authenticated,
        avs_result=transaction.avs_result,
        cvv_result=transaction.cvv_result,
        account_age_days=customer.account_age_days,
        previous_order_count=customer.previous_order_count,
        previous_successful_order_count=customer.previous_successful_order_count,
        previous_dispute_count=customer.previous_dispute_count,
        previous_refund_count=customer.previous_refund_count,
        evidence_rows=evidence_rows,
        reference=reference,
    )


def get_case_gap(db: Session, case_id: str) -> EvidenceGapResult:
    """Part A standalone: gap analysis only (no packet/retrieval overhead)."""
    dispute, evidence_rows = _load_case(db, case_id)
    state = case_evidence_state_from_rows(evidence_rows)
    return analyze_gap(dispute.reason_code, state)


class DraftResult:
    """Everything POST /cases/{id}/draft returns, assembled in one place."""

    def __init__(
        self,
        *,
        case_id: str,
        reason_code: str,
        decision: dict | None,
        packet: EvidencePacket,
        retrieval_results: list[RetrievalResult],
        generation_available: bool,
        draft: GeneratedDraft | None,
        verifications: list[ClaimVerification],
        response_state: str,
        response_state_reason: str,
        trace: ResponseTrace,
        error: str | None = None,
        generation_error_kind: str | None = None,
    ) -> None:
        self.case_id = case_id
        self.reason_code = reason_code
        self.decision = decision
        self.packet = packet
        self.retrieval_results = retrieval_results
        self.generation_available = generation_available
        self.draft = draft
        self.verifications = verifications
        self.response_state = response_state
        self.response_state_reason = response_state_reason
        self.trace = trace
        self.error = error
        #: Additive classification of WHY generation produced no draft --
        #: 'provider_unavailable' or 'invalid_output'. None when generation
        #: succeeded or was never attempted. response_state is unchanged by
        #: this field; it exists so the UI can distinguish a provider outage
        #: from a verifier rejection instead of showing both as 'blocked'.
        self.generation_error_kind = generation_error_kind


def generate_case_draft(
    db: Session,
    case_id: str,
    *,
    risk_model: RiskModel,
    decision_config: DecisionConfig,
    llm_provider: LLMProvider | None,
    top_k_retrieval: int = 6,
) -> DraftResult:
    """The full Phase 4 pipeline for one case.

    Reuses Phase 3's decide_case() for the decision (never recomputed here),
    then runs gap analysis -> packet -> retrieval -> generation (if a
    provider is configured) -> verification -> safety -> trace.
    """
    decision_payload = decide_case(db, case_id, risk_model, decision_config)
    packet = build_case_packet(db, case_id)
    retrieval_results = retrieve_for_case(reason_code=packet.case.reason_code, gap=packet.gap, top_k=top_k_retrieval)

    if llm_provider is None:
        response_state = v.GENERATION_UNAVAILABLE
        reason = (
            "No LLM provider is configured (set LLM_PROVIDER + OPENROUTER_API_KEY, or LLM_PROVIDER=anthropic "
            "+ ANTHROPIC_API_KEY). Evidence-gap analysis, the evidence packet, and retrieval above are fully "
            "available; response generation is not."
        )
        trace = build_trace(
            case_id=case_id,
            decision=decision_payload["decision"],
            decision_policy_version=decision_payload["decision_policy_version"],
            retrieved_source_ids=[r.source_id for r in retrieval_results],
            retrieved_chunk_ids=[r.chunk_id for r in retrieval_results],
            cited_evidence_ids=[],
            claim_statuses={},
            response_state=response_state,
        )
        return DraftResult(
            case_id=case_id,
            reason_code=packet.case.reason_code,
            decision=decision_payload,
            packet=packet,
            retrieval_results=retrieval_results,
            generation_available=False,
            draft=None,
            verifications=[],
            response_state=response_state,
            response_state_reason=reason,
            trace=trace,
        )

    try:
        draft = generate_draft(packet, retrieval_results, llm_provider)
    except LLMOutputError as exc:
        # response_state stays DRAFT_BLOCKED for every generation failure --
        # the Phase 4 contract is unchanged. Only the reporting is sharper.
        response_state = v.DRAFT_BLOCKED
        error_kind = "provider_unavailable" if isinstance(exc, ProviderUnavailableError) else (
            "invalid_output" if isinstance(exc, InvalidOutputError) else None
        )
        reason = f"Generation failed: {exc}"
        trace = build_trace(
            case_id=case_id,
            decision=decision_payload["decision"],
            decision_policy_version=decision_payload["decision_policy_version"],
            retrieved_source_ids=[r.source_id for r in retrieval_results],
            retrieved_chunk_ids=[r.chunk_id for r in retrieval_results],
            cited_evidence_ids=[],
            claim_statuses={},
            response_state=response_state,
        )
        return DraftResult(
            case_id=case_id,
            reason_code=packet.case.reason_code,
            decision=decision_payload,
            packet=packet,
            retrieval_results=retrieval_results,
            generation_available=True,
            draft=None,
            verifications=[],
            response_state=response_state,
            response_state_reason=reason,
            trace=trace,
            error=str(exc),
            generation_error_kind=error_kind,
        )

    verifications = verify_claims(draft.claims, packet, retrieval_results)
    # verifier-v1.1: the overall response_body isn't a claims[] entry, so it
    # gets its own completeness check, appended alongside the per-claim ones
    # so determine_response_state() sees it too (a dangling response_body
    # blocks the draft even if every individual claim's own text is fine).
    verifications = verifications + [verify_response_body(draft.response_body)]
    response_state, reason = determine_response_state(verifications)

    claim_statuses: dict[str, int] = {}
    for verification in verifications:
        claim_statuses[verification.status] = claim_statuses.get(verification.status, 0) + 1
    cited_evidence_ids = [e for verification in verifications for e in verification.evidence_ids]

    trace = build_trace(
        case_id=case_id,
        decision=decision_payload["decision"],
        decision_policy_version=decision_payload["decision_policy_version"],
        retrieved_source_ids=[r.source_id for r in retrieval_results],
        retrieved_chunk_ids=[r.chunk_id for r in retrieval_results],
        cited_evidence_ids=cited_evidence_ids,
        claim_statuses=claim_statuses,
        response_state=response_state,
    )

    return DraftResult(
        case_id=case_id,
        reason_code=packet.case.reason_code,
        decision=decision_payload,
        packet=packet,
        retrieval_results=retrieval_results,
        generation_available=True,
        draft=draft,
        verifications=verifications,
        response_state=response_state,
        response_state_reason=reason,
        trace=trace,
    )


def verify_case_claims(
    db: Session,
    case_id: str,
    claims_payload: list[dict],
    *,
    top_k_retrieval: int = 6,
) -> tuple[EvidencePacket, list[RetrievalResult], list[ClaimVerification], str, str]:
    """Part F/I standalone endpoint: verify externally-supplied claims (e.g. a
    human-edited draft) against this case's own, freshly-rebuilt packet --
    independent of whether/how the claims were originally generated."""
    from app.evidence_intel.generation import GeneratedClaim

    packet = build_case_packet(db, case_id)
    retrieval_results = retrieve_for_case(reason_code=packet.case.reason_code, gap=packet.gap, top_k=top_k_retrieval)

    claims = [GeneratedClaim.model_validate(c) for c in claims_payload]
    verifications = verify_claims(claims, packet, retrieval_results)
    response_state, reason = determine_response_state(verifications)

    return packet, retrieval_results, verifications, response_state, reason
