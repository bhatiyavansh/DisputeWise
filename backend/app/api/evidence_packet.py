from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.evidence_gap import _to_response as gap_to_response
from app.db.session import get_db
from app.evidence_intel.packet import EvidencePacket
from app.schemas.evidence_intel import (
    EvidencePacketItemResponse,
    EvidencePacketResponse,
    ReasonCodeGuidanceResponse,
)
from app.services.evidence_intel_service import build_case_packet
from app.services.scoring_service import CaseNotFoundError

router = APIRouter(tags=["evidence-intelligence"])


def _to_response(packet: EvidencePacket) -> EvidencePacketResponse:
    return EvidencePacketResponse(
        case_id=packet.case.dispute_id,
        schema_version=packet.schema_version,
        generated_at=packet.generated_at,
        reason_code=packet.case.reason_code,
        dispute_amount=packet.case.dispute_amount,
        dispute_status=packet.case.dispute_status,
        transaction=vars(packet.transaction),
        customer=vars(packet.customer),
        evidence=[EvidencePacketItemResponse(**vars(item)) for item in packet.evidence],
        gap=gap_to_response(packet.case.dispute_id, packet.gap),
        guidance=ReasonCodeGuidanceResponse(**vars(packet.guidance)),
    )


@router.post("/cases/{case_id}/evidence-packet", response_model=EvidencePacketResponse)
def evidence_packet_endpoint(case_id: str, db: Session = Depends(get_db)) -> EvidencePacketResponse:
    """The full, LLM-safe evidence packet for a case: case/transaction/customer
    facts (narrow, no raw PII/identifiers), every evidence item with its
    stable evidence_id, the evidence-gap analysis, and reason-code guidance
    with provenance. This is exactly what response generation is given --
    nothing more.
    """
    try:
        packet = build_case_packet(db, case_id)
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return _to_response(packet)
