"""Part C (knowledge base) + Part D (retrieval) + provenance tests."""

from app.evidence_intel.gap_analyzer import analyze_gap
from app.evidence_intel.knowledge_base import KnowledgeBase, build_chunks, get_knowledge_base
from app.evidence_intel.retrieval import build_query, retrieve_for_case


# ---------------------------------------------------------------------------
# Knowledge base construction (Part C)
# ---------------------------------------------------------------------------


def test_chunk_count_matches_reference_data():
    chunks = build_chunks()
    # 3 reason-code chunks + 48 evidence-requirement chunks (3 reason codes x 16 evidence types)
    assert len(chunks) == 3 + 48


def test_chunk_ids_are_unique():
    chunks = build_chunks()
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_chunk_construction_is_deterministic():
    first = build_chunks()
    second = build_chunks()
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
    assert [c.text for c in first] == [c.text for c in second]


def test_every_chunk_has_provenance():
    for chunk in build_chunks():
        assert chunk.source_id
        assert chunk.source_name
        assert chunk.source_url.startswith("https://")


def test_evidence_requirement_chunks_carry_reason_code_and_evidence_type():
    chunks = build_chunks()
    evidence_chunks = [c for c in chunks if c.doc_type == "evidence_requirement"]
    assert len(evidence_chunks) == 48
    assert all(c.evidence_type is not None and c.relevance is not None for c in evidence_chunks)


def test_knowledge_base_version_is_set():
    kb = get_knowledge_base()
    assert kb.version == "knowledge-v1"


def test_get_knowledge_base_is_cached_singleton():
    assert get_knowledge_base() is get_knowledge_base()


# ---------------------------------------------------------------------------
# Retrieval (Part D)
# ---------------------------------------------------------------------------


def test_search_filters_by_reason_code_before_ranking():
    kb = KnowledgeBase(build_chunks())
    results = kb.search("evidence", reason_code="duplicate_charge", top_k=50)
    assert all(chunk.reason_code_id == "duplicate_charge" for chunk, _ in results)


def test_search_without_reason_code_searches_everything():
    kb = KnowledgeBase(build_chunks())
    results = kb.search("evidence", reason_code=None, top_k=100)
    reason_codes = {chunk.reason_code_id for chunk, _ in results}
    assert len(reason_codes) > 1


def test_search_respects_top_k():
    kb = KnowledgeBase(build_chunks())
    results = kb.search("delivery", reason_code="goods_not_received", top_k=3)
    assert len(results) <= 3


def test_build_query_includes_reason_code_and_gaps():
    query = build_query("goods_not_received", ["proof_of_delivery"])
    assert "goods not received" in query
    assert "proof of delivery" in query


def test_build_query_handles_no_gaps():
    query = build_query("goods_not_received", [])
    assert query == "goods not received"


def test_retrieval_surfaces_the_actual_gap_as_top_hit():
    """The headline retrieval behavior from docs/phase4.md / the demo case:
    when proof_of_delivery is missing, it should rank at or near the top of
    retrieved guidance for a goods_not_received case."""
    state = {}  # nothing available -> everything required is "missing"
    gap = analyze_gap("goods_not_received", state)
    results = retrieve_for_case(reason_code="goods_not_received", gap=gap, top_k=3)
    assert results
    top_chunk_ids = [r.chunk_id for r in results[:3]]
    assert any("proof_of_delivery" in chunk_id for chunk_id in top_chunk_ids)


def test_retrieval_results_are_reason_code_scoped():
    state = {}
    gap = analyze_gap("unauthorized_transaction", state)
    results = retrieve_for_case(reason_code="unauthorized_transaction", gap=gap, top_k=10)
    assert all(r.metadata["reason_code_id"] == "unauthorized_transaction" for r in results)


def test_retrieval_results_carry_full_provenance():
    state = {}
    gap = analyze_gap("duplicate_charge", state)
    results = retrieve_for_case(reason_code="duplicate_charge", gap=gap, top_k=5)
    for r in results:
        assert r.chunk_id
        assert r.text
        assert r.source_id
        assert r.source_name
        assert r.source_url
        assert isinstance(r.relevance_score, float)
        assert "doc_type" in r.metadata


def test_retrieval_marks_which_results_address_a_gap():
    state = {}
    gap = analyze_gap("goods_not_received", state)
    results = retrieve_for_case(reason_code="goods_not_received", gap=gap, top_k=10)
    assert any(r.metadata["addresses_gap"] for r in results)


def test_retrieval_deterministic():
    state = {}
    gap = analyze_gap("goods_not_received", state)
    first = retrieve_for_case(reason_code="goods_not_received", gap=gap, top_k=5)
    second = retrieve_for_case(reason_code="goods_not_received", gap=gap, top_k=5)
    assert [r.chunk_id for r in first] == [r.chunk_id for r in second]
    assert [r.relevance_score for r in first] == [r.relevance_score for r in second]
