"""Part H -- "Why this response?" trace.

A concise, structured, fully-auditable record of what produced a draft --
NOT hidden chain-of-thought. Every field here is either a version string, an
ID, or a deterministic fact already computed elsewhere; nothing here is raw
model reasoning text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.evidence_intel import versions as v
from app.ml import schema as ml_schema


@dataclass(frozen=True)
class ResponseTrace:
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
    claim_statuses: dict[str, int]  # status -> count
    response_state: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def build_trace(
    *,
    case_id: str,
    decision: str | None,
    decision_policy_version: str | None,
    retrieved_source_ids: list[str],
    retrieved_chunk_ids: list[str],
    cited_evidence_ids: list[str],
    claim_statuses: dict[str, int],
    response_state: str,
) -> ResponseTrace:
    return ResponseTrace(
        case_id=case_id,
        decision=decision,
        model_version=ml_schema.MODEL_VERSION,
        feature_schema_version=ml_schema.FEATURE_SCHEMA_VERSION,
        decision_policy_version=decision_policy_version,
        evidence_schema_version=v.EVIDENCE_SCHEMA_VERSION,
        knowledge_base_version=v.KNOWLEDGE_BASE_VERSION,
        retrieval_config_version=v.RETRIEVAL_CONFIG_VERSION,
        prompt_version=v.PROMPT_VERSION,
        response_schema_version=v.RESPONSE_SCHEMA_VERSION,
        verifier_version=v.VERIFIER_VERSION,
        retrieved_source_ids=sorted(set(retrieved_source_ids)),
        retrieved_chunk_ids=sorted(set(retrieved_chunk_ids)),
        cited_evidence_ids=sorted(set(cited_evidence_ids)),
        claim_count=sum(claim_statuses.values()),
        claim_statuses=claim_statuses,
        response_state=response_state,
    )
