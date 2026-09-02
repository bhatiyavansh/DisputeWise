"""Part B -- Evidence Packet.

Combines everything downstream generation/verification needs about ONE case
into a single, serializable, LLM-safe object. Deliberately narrow: this is
NOT a database row dump. Excluded on purpose:

  - raw device_id / ip_address (only their derived match booleans are
    evidence; the identifiers themselves are neither useful to a response
    draft nor safe to hand to an external LLM API)
  - billing/shipping address IDs (same reasoning)
  - customer country (excluded from Phase 2 features on fairness grounds;
    same rationale applies here -- no reason a dispute-response draft needs it)
  - the ML target / outcome fields (favorable_outcome, recovery_amount,
    outcome_at, outcome_source) -- this packet is built for a case that has
    not been decided yet; those fields must never be reachable here, mirroring
    the structural leakage guard in app/ml/features.build_features()

Every evidence item keeps its real, stable evidence_id from the database
(EVD-xxxxxxx) -- claim verification later cites these IDs directly, and a
citation of an ID that isn't in THIS packet is exactly how cross-case
evidence contamination and fabricated-evidence-ID attacks get caught.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from app.evidence_intel import versions as v
from app.evidence_intel.gap_analyzer import EvidenceGapResult, analyze_gap, case_evidence_state_from_rows
from app.evidence_intel.reference_data import ReferenceData, load_reference_data


@dataclass(frozen=True)
class EvidencePacketItem:
    evidence_id: str
    evidence_type: str
    available: bool
    value: dict | None
    relevance: str  # high | medium | low, as stored on the case's own evidence row
    strength: float
    claim_type: str = v.CLAIM_TYPE_FACT  # evidence items are always FACT: on file for this case


@dataclass(frozen=True)
class CaseFacts:
    dispute_id: str
    reason_code: str
    dispute_amount: float
    dispute_status: str
    created_at: str


@dataclass(frozen=True)
class TransactionFacts:
    payment_method: str
    transaction_status: str
    three_ds_authenticated: bool
    avs_result: str
    cvv_result: str


@dataclass(frozen=True)
class CustomerFacts:
    """Behavioral history only -- no raw PII, no location. See module docstring."""

    account_age_days: int
    previous_order_count: int
    previous_successful_order_count: int
    previous_dispute_count: int
    previous_refund_count: int


@dataclass(frozen=True)
class ReasonCodeGuidance:
    reason_code_id: str
    reason_code_name: str
    description: str
    source_id: str
    claim_type: str = v.CLAIM_TYPE_REFERENCE


@dataclass(frozen=True)
class EvidencePacket:
    schema_version: str
    generated_at: str
    case: CaseFacts
    transaction: TransactionFacts
    customer: CustomerFacts
    evidence: list[EvidencePacketItem]
    gap: EvidenceGapResult
    guidance: ReasonCodeGuidance

    def evidence_by_id(self) -> dict[str, EvidencePacketItem]:
        return {item.evidence_id: item for item in self.evidence}

    def to_dict(self) -> dict:
        payload = asdict(self)
        # dataclasses.asdict recurses into EvidenceGapResult's dataclass fields too
        return payload


def build_packet(
    *,
    dispute_id: str,
    reason_code: str,
    dispute_amount: float,
    dispute_status: str,
    created_at: str,
    payment_method: str,
    transaction_status: str,
    three_ds_authenticated: bool,
    avs_result: str,
    cvv_result: str,
    account_age_days: int,
    previous_order_count: int,
    previous_successful_order_count: int,
    previous_dispute_count: int,
    previous_refund_count: int,
    evidence_rows: list,
    reference: ReferenceData | None = None,
) -> EvidencePacket:
    reference = reference or load_reference_data()

    case_evidence_state = case_evidence_state_from_rows(evidence_rows)
    gap = analyze_gap(reason_code, case_evidence_state, reference)

    reason_info = reference.reason_codes.get(reason_code)
    if reason_info is None:
        raise ValueError(f"no reference reason-code entry for '{reason_code}'")

    evidence_items = [
        EvidencePacketItem(
            evidence_id=row.evidence_id,
            evidence_type=row.evidence_type,
            available=bool(row.available),
            value=row.value,
            relevance=row.relevance,
            strength=float(row.strength or 0.0),
        )
        for row in sorted(evidence_rows, key=lambda r: r.evidence_type)
    ]

    return EvidencePacket(
        schema_version=v.EVIDENCE_SCHEMA_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        case=CaseFacts(
            dispute_id=dispute_id,
            reason_code=reason_code,
            dispute_amount=float(dispute_amount) if isinstance(dispute_amount, Decimal) else dispute_amount,
            dispute_status=dispute_status,
            created_at=created_at,
        ),
        transaction=TransactionFacts(
            payment_method=payment_method,
            transaction_status=transaction_status,
            three_ds_authenticated=three_ds_authenticated,
            avs_result=avs_result,
            cvv_result=cvv_result,
        ),
        customer=CustomerFacts(
            account_age_days=account_age_days,
            previous_order_count=previous_order_count,
            previous_successful_order_count=previous_successful_order_count,
            previous_dispute_count=previous_dispute_count,
            previous_refund_count=previous_refund_count,
        ),
        evidence=evidence_items,
        gap=gap,
        guidance=ReasonCodeGuidance(
            reason_code_id=reason_info.reason_code_id,
            reason_code_name=reason_info.reason_code_name,
            description=reason_info.description,
            source_id=reason_info.source_id,
        ),
    )
