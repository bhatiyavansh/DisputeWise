"""Part C -- RAG knowledge base.

Deliberately the simplest architecture that is reliable locally: the entire
corpus is the ~51 rows of `data/reference/` (3 reason-code descriptions + 48
evidence-requirement descriptions), which does not warrant a managed vector
database, an embedding model download, or any persisted index file. Chunks
are (re)built deterministically from the versioned CSVs every time the
process starts, and ranked with TF-IDF + cosine similarity (scikit-learn is
already a Phase 2 dependency -- no new heavy dependency added for this).

Rebuildability: `build_knowledge_base()` is a pure function of
data/reference/*.csv content. Same reference data in -> same chunk set and
same chunk_ids out, every time -- that's the whole "rebuild from versioned
reference data" requirement, satisfied without a build step or artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.evidence_intel import versions as v
from app.evidence_intel.reference_data import ReferenceData, load_reference_data


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    text: str
    doc_type: str  # "reason_code" | "evidence_requirement"
    reason_code_id: str
    evidence_type: str | None
    relevance: str | None  # only set for evidence_requirement chunks
    source_id: str
    source_name: str
    source_url: str


def build_chunks(reference: ReferenceData | None = None) -> list[KnowledgeChunk]:
    """Deterministic chunk construction. Sorted by chunk_id for reproducibility."""
    reference = reference or load_reference_data()
    chunks: list[KnowledgeChunk] = []

    for reason_code_id, info in reference.reason_codes.items():
        source = reference.source(info.source_id)
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"reason:{reason_code_id}",
                text=f"{info.reason_code_name}. {info.description} (Network examples: {info.network_examples}.)",
                doc_type="reason_code",
                reason_code_id=reason_code_id,
                evidence_type=None,
                relevance=None,
                source_id=info.source_id,
                source_name=source.source_name if source else "",
                source_url=source.source_url if source else "",
            )
        )

    for requirement in reference.evidence_requirements:
        source = reference.source(requirement.source_id)
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"evidence:{requirement.reason_code_id}:{requirement.evidence_type}",
                text=(
                    f"For {requirement.reason_code_id.replace('_', ' ')} disputes, "
                    f"{requirement.evidence_type.replace('_', ' ')} evidence is {requirement.relevance} "
                    f"relevance. {requirement.description}"
                ),
                doc_type="evidence_requirement",
                reason_code_id=requirement.reason_code_id,
                evidence_type=requirement.evidence_type,
                relevance=requirement.relevance,
                source_id=requirement.source_id,
                source_name=source.source_name if source else "",
                source_url=source.source_url if source else "",
            )
        )

    return sorted(chunks, key=lambda c: c.chunk_id)


class KnowledgeBase:
    version = v.KNOWLEDGE_BASE_VERSION

    def __init__(self, chunks: list[KnowledgeChunk]) -> None:
        self.chunks = chunks
        self._vectorizer = TfidfVectorizer(stop_words="english")
        self._matrix = self._vectorizer.fit_transform([c.text for c in chunks]) if chunks else None

    def chunk_ids(self) -> set[str]:
        return {c.chunk_id for c in self.chunks}

    def search(self, query: str, *, reason_code: str | None = None, top_k: int = 5) -> list[tuple[KnowledgeChunk, float]]:
        """Reason-code metadata filter first (deterministic), THEN TF-IDF
        cosine ranking within that filtered subset -- never unrestricted
        vector search over the whole corpus when a reason code is known."""
        if self._matrix is None:
            return []

        candidate_indices = [
            i for i, c in enumerate(self.chunks) if reason_code is None or c.reason_code_id == reason_code
        ]
        if not candidate_indices:
            return []

        query_vector = self._vectorizer.transform([query])
        scores = cosine_similarity(query_vector, self._matrix[candidate_indices])[0]

        ranked = sorted(
            zip((self.chunks[i] for i in candidate_indices), scores),
            key=lambda pair: (-pair[1], pair[0].chunk_id),
        )
        return [(chunk, float(score)) for chunk, score in ranked[:top_k]]


@lru_cache(maxsize=1)
def get_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase(build_chunks())
