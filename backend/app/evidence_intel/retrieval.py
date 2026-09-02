"""Part D -- retrieval for a specific dispute.

Query construction is deterministic (built from the reason code + the case's
own missing-evidence types -- see gap_analyzer.py), not left to an LLM's
judgment of what's relevant. Results are plain, inspectable data: every
result carries its source chunk text and provenance, so a caller (API,
frontend, or test) can see exactly why each chunk was retrieved.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.evidence_intel import versions as v
from app.evidence_intel.gap_analyzer import EvidenceGapResult
from app.evidence_intel.knowledge_base import KnowledgeBase, get_knowledge_base

DEFAULT_TOP_K = 6


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: str
    text: str
    source_id: str
    source_name: str
    source_url: str
    relevance_score: float
    metadata: dict


def build_query(reason_code: str, missing_evidence_types: list[str]) -> str:
    """Deterministic query text: reason code + the gaps we most need guidance on."""
    reason_phrase = reason_code.replace("_", " ")
    if not missing_evidence_types:
        return reason_phrase
    gap_phrase = " ".join(t.replace("_", " ") for t in missing_evidence_types)
    return f"{reason_phrase} {gap_phrase}"


def retrieve_for_case(
    *,
    reason_code: str,
    gap: EvidenceGapResult,
    top_k: int = DEFAULT_TOP_K,
    knowledge_base: KnowledgeBase | None = None,
) -> list[RetrievalResult]:
    """Reason-code-filtered, gap-aware retrieval of authoritative guidance."""
    kb = knowledge_base or get_knowledge_base()
    missing_types = [item.evidence_type for item in gap.items if item.status == v.STATUS_MISSING and item.required]
    query = build_query(reason_code, missing_types)

    hits = kb.search(query, reason_code=reason_code, top_k=top_k)

    return [
        RetrievalResult(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            source_id=chunk.source_id,
            source_name=chunk.source_name,
            source_url=chunk.source_url,
            relevance_score=round(score, 6),
            metadata={
                "doc_type": chunk.doc_type,
                "reason_code_id": chunk.reason_code_id,
                "evidence_type": chunk.evidence_type,
                "relevance": chunk.relevance,
                "addresses_gap": chunk.evidence_type in missing_types,
            },
        )
        for chunk, score in hits
    ]
