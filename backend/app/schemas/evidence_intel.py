from pydantic import BaseModel, Field

from app.evidence_intel import versions as v


class GapItemResponse(BaseModel):
    evidence_type: str
    required: bool
    status: str = Field(description="AVAILABLE | MISSING")
    relevance: str = Field(description="HIGH | MEDIUM | LOW")
    priority: str = Field(description="CRITICAL | IMPORTANT | OPTIONAL | NONE")
    reason: str
    source_id: str
    strength: float
    evidence_id: str | None


class EvidenceGapResponse(BaseModel):
    case_id: str
    reason_code: str
    schema_version: str
    coverage: dict[str, int]
    coverage_ratio: float
    items: list[GapItemResponse]


class EvidencePacketItemResponse(BaseModel):
    evidence_id: str
    evidence_type: str
    available: bool
    value: dict | None
    relevance: str
    strength: float
    claim_type: str


class ReasonCodeGuidanceResponse(BaseModel):
    reason_code_id: str
    reason_code_name: str
    description: str
    source_id: str
    claim_type: str


class EvidencePacketResponse(BaseModel):
    case_id: str
    schema_version: str
    generated_at: str
    reason_code: str
    dispute_amount: float
    dispute_status: str
    transaction: dict
    customer: dict
    evidence: list[EvidencePacketItemResponse]
    gap: EvidenceGapResponse
    guidance: ReasonCodeGuidanceResponse


class RetrievalResultResponse(BaseModel):
    chunk_id: str
    text: str
    source_id: str
    source_name: str
    source_url: str
    relevance_score: float
    metadata: dict


class GeneratedClaimResponse(BaseModel):
    claim_id: str
    text: str
    claim_type: str
    evidence_ids: list[str]
    source_ids: list[str]


class ClaimVerificationResponse(BaseModel):
    claim_id: str
    status: str = Field(description="SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED | INVALID_REFERENCE | INCOMPLETE")
    evidence_ids: list[str]
    source_ids: list[str]
    explanation: str
    verifier_version: str


class ResponseTraceResponse(BaseModel):
    case_id: str
    decision: str | None
    model_version: str
    feature_schema_version: str
    decision_policy_version: str | None
    evidence_schema_version: str
    knowledge_base_version: str
    retrieval_config_version: str
    prompt_version: str
    response_schema_version: str
    verifier_version: str
    retrieved_source_ids: list[str]
    retrieved_chunk_ids: list[str]
    cited_evidence_ids: list[str]
    claim_count: int
    claim_statuses: dict[str, int]
    response_state: str
    generated_at: str


class DecisionSummaryResponse(BaseModel):
    decision: str
    calibrated_probability: float
    expected_net_value: float
    risk_band: str


class DraftResponse(BaseModel):
    case_id: str
    reason_code: str

    model_version: str
    feature_schema_version: str
    decision_policy_version: str | None
    evidence_schema_version: str
    knowledge_base_version: str
    prompt_version: str
    response_schema_version: str
    verifier_version: str

    decision: DecisionSummaryResponse | None
    evidence_gap: EvidenceGapResponse
    retrieved_sources: list[RetrievalResultResponse]

    generation_available: bool
    summary: str | None
    claims: list[GeneratedClaimResponse]
    missing_evidence: list[str]
    response_body: str | None

    claim_verifications: list[ClaimVerificationResponse]
    response_state: str = Field(description="DRAFT_READY | DRAFT_FLAGGED | DRAFT_BLOCKED | GENERATION_UNAVAILABLE")
    response_state_reason: str

    trace: ResponseTraceResponse
    disclaimer: str = v.DISCLAIMER


class VerifyRequestClaim(BaseModel):
    claim_id: str
    text: str
    claim_type: str
    evidence_ids: list[str] = []
    source_ids: list[str] = []


class VerifyRequest(BaseModel):
    claims: list[VerifyRequestClaim]


class VerifyResponse(BaseModel):
    case_id: str
    verifier_version: str
    claim_verifications: list[ClaimVerificationResponse]
    response_state: str
    response_state_reason: str
    disclaimer: str = v.DISCLAIMER
