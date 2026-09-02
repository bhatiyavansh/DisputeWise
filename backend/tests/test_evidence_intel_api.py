"""API-level tests for the four Phase 4 endpoints:
    POST /cases/{id}/evidence-gap
    POST /cases/{id}/evidence-packet
    POST /cases/{id}/draft
    POST /cases/{id}/verify

Also covers: version metadata presence, determinism, unknown-case handling,
and that /draft never silently fabricates a decision/generation result when
its dependencies are unavailable.
"""

import pytest

from app.evidence_intel.llm_provider import FakeLLMProvider
from app.api.drafts import get_optional_llm_provider
from app.main import app
from tests.factories import add_evidence, make_case

pytest.importorskip("lightgbm")
pytest.importorskip("shap")


@pytest.fixture()
def case_with_gap(db_session):
    dispute = make_case(db_session, dispute_id="DSP-000001", reason_code="goods_not_received")
    # make_case already adds one 'delivery_confirmed' (high, available) row;
    # add a couple more so the packet/draft pipeline has enough to work with.
    add_evidence(
        db_session, dispute, evidence_type="delivery_timestamp", available=True,
        value={"timestamp": "2026-01-05T00:00:00+00:00"}, relevance="high", strength=0.8,
        evidence_id="EVD-TIMESTAMP-001",
    )
    add_evidence(
        db_session, dispute, evidence_type="proof_of_delivery", available=False, value=None,
        relevance="high", strength=0.0, evidence_id="EVD-POD-001",
    )
    return dispute


@pytest.fixture(autouse=True)
def _clear_llm_override():
    yield
    app.dependency_overrides.pop(get_optional_llm_provider, None)


# ---------------------------------------------------------------------------
# /evidence-gap
# ---------------------------------------------------------------------------


def test_evidence_gap_endpoint_returns_200(client, case_with_gap):
    resp = client.post("/cases/DSP-000001/evidence-gap")
    assert resp.status_code == 200
    body = resp.json()
    assert body["case_id"] == "DSP-000001"
    assert body["reason_code"] == "goods_not_received"
    assert body["coverage"]["missing"] >= 1


def test_evidence_gap_endpoint_unknown_case_404(client, db_session):
    resp = client.post("/cases/DSP-999999/evidence-gap")
    assert resp.status_code == 404


def test_evidence_gap_flags_proof_of_delivery_as_critical(client, case_with_gap):
    body = client.post("/cases/DSP-000001/evidence-gap").json()
    item = next(i for i in body["items"] if i["evidence_type"] == "proof_of_delivery")
    assert item["status"] == "MISSING"
    assert item["priority"] == "CRITICAL"
    assert item["source_id"]


# ---------------------------------------------------------------------------
# /evidence-packet
# ---------------------------------------------------------------------------


def test_evidence_packet_endpoint_returns_200(client, case_with_gap):
    resp = client.post("/cases/DSP-000001/evidence-packet")
    assert resp.status_code == 200
    body = resp.json()
    assert body["case_id"] == "DSP-000001"
    assert len(body["evidence"]) >= 3
    assert body["gap"]["coverage"]["missing"] >= 1
    assert body["guidance"]["reason_code_id"] == "goods_not_received"


def test_evidence_packet_endpoint_unknown_case_404(client, db_session):
    resp = client.post("/cases/DSP-999999/evidence-packet")
    assert resp.status_code == 404


def test_evidence_packet_excludes_raw_pii(client, case_with_gap):
    resp = client.post("/cases/DSP-000001/evidence-packet")
    serialized = resp.text
    for forbidden in ("device_id", "ip_address", "\"country\"", "billing_address", "shipping_address"):
        assert forbidden not in serialized


# ---------------------------------------------------------------------------
# /draft
# ---------------------------------------------------------------------------


def test_draft_endpoint_returns_generation_unavailable_without_provider(client, case_with_gap, risk_model):
    app.dependency_overrides[get_optional_llm_provider] = lambda: None
    resp = client.post("/cases/DSP-000001/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert body["response_state"] == "GENERATION_UNAVAILABLE"
    assert body["generation_available"] is False
    assert body["claims"] == []
    assert body["response_body"] is None
    # but decision/evidence-gap/retrieval are still fully present
    assert body["decision"]["decision"] in ("CONTEST", "HUMAN_REVIEW", "DO_NOT_CONTEST")
    assert body["evidence_gap"]["coverage"]["missing"] >= 1
    assert len(body["retrieved_sources"]) > 0


def test_draft_endpoint_with_fake_provider_returns_ready(client, case_with_gap, risk_model):
    def _fake_provider():
        return FakeLLMProvider(
            response={
                "summary": "s",
                "claims": [
                    {"claim_id": "C1", "text": "Delivery was confirmed.", "claim_type": "fact", "evidence_ids": [], "source_ids": ["stripe_dispute_reason_codes_2026"]}
                ],
                "missing_evidence": ["proof_of_delivery"],
                "response_body": "Body text.",
            }
        )

    app.dependency_overrides[get_optional_llm_provider] = _fake_provider
    resp = client.post("/cases/DSP-000001/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert body["generation_available"] is True
    assert body["response_state"] == "DRAFT_READY"
    # verifier-v1.1: one verification per claim, plus one synthetic
    # RESPONSE_BODY completeness check -- both SUPPORTED here since
    # "Body text." (the claim and the response_body) are complete sentences.
    assert len(body["claim_verifications"]) == 2
    statuses_by_id = {c["claim_id"]: c["status"] for c in body["claim_verifications"]}
    assert statuses_by_id["C1"] == "SUPPORTED"
    assert statuses_by_id["RESPONSE_BODY"] == "SUPPORTED"


def test_draft_endpoint_blocks_on_unsupported_claim(client, case_with_gap, risk_model):
    def _fake_provider():
        return FakeLLMProvider(
            response={
                "summary": "s",
                "claims": [
                    {"claim_id": "C1", "text": "Proof of delivery confirms receipt.", "claim_type": "fact", "evidence_ids": ["EVD-POD-001"], "source_ids": []}
                ],
                "missing_evidence": [],
                "response_body": "Body text.",
            }
        )

    app.dependency_overrides[get_optional_llm_provider] = _fake_provider
    resp = client.post("/cases/DSP-000001/draft")
    body = resp.json()
    assert body["response_state"] == "DRAFT_BLOCKED"
    assert body["claim_verifications"][0]["status"] == "UNSUPPORTED"


def test_draft_endpoint_unknown_case_404(client, db_session, risk_model):
    resp = client.post("/cases/DSP-999999/draft")
    assert resp.status_code == 404


def test_draft_endpoint_includes_version_metadata(client, case_with_gap, risk_model):
    app.dependency_overrides[get_optional_llm_provider] = lambda: None
    body = client.post("/cases/DSP-000001/draft").json()
    for field in (
        "model_version", "feature_schema_version", "decision_policy_version",
        "evidence_schema_version", "knowledge_base_version", "prompt_version",
        "response_schema_version", "verifier_version",
    ):
        assert body[field], field


def test_draft_endpoint_includes_disclaimer_about_no_auto_submission(client, case_with_gap, risk_model):
    app.dependency_overrides[get_optional_llm_provider] = lambda: None
    body = client.post("/cases/DSP-000001/draft").json()
    disclaimer = body["disclaimer"].lower()
    assert "not" in disclaimer
    assert "automatically" in disclaimer or "human" in disclaimer


def test_draft_endpoint_deterministic_without_provider(client, case_with_gap, risk_model):
    app.dependency_overrides[get_optional_llm_provider] = lambda: None
    first = client.post("/cases/DSP-000001/draft").json()
    second = client.post("/cases/DSP-000001/draft").json()
    assert first["evidence_gap"] == second["evidence_gap"]
    assert first["retrieved_sources"] == second["retrieved_sources"]
    assert first["decision"] == second["decision"]


# ---------------------------------------------------------------------------
# /verify
# ---------------------------------------------------------------------------


def test_verify_endpoint_supported_claim(client, case_with_gap):
    resp = client.post(
        "/cases/DSP-000001/verify",
        json={"claims": [{"claim_id": "C1", "text": "Delivery confirmed.", "claim_type": "fact", "evidence_ids": ["EVD-DSP-000001-01"], "source_ids": []}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["claim_verifications"][0]["status"] == "SUPPORTED"
    assert body["response_state"] == "DRAFT_READY"


def test_verify_endpoint_invalid_reference(client, case_with_gap):
    resp = client.post(
        "/cases/DSP-000001/verify",
        json={"claims": [{"claim_id": "C1", "text": "x", "claim_type": "fact", "evidence_ids": ["EVD-NOT-REAL"], "source_ids": []}]},
    )
    body = resp.json()
    assert body["claim_verifications"][0]["status"] == "INVALID_REFERENCE"
    assert body["response_state"] == "DRAFT_BLOCKED"


def test_verify_endpoint_unknown_case_404(client, db_session):
    resp = client.post("/cases/DSP-999999/verify", json={"claims": []})
    assert resp.status_code == 404


def test_verify_endpoint_no_claims_is_blocked(client, case_with_gap):
    resp = client.post("/cases/DSP-000001/verify", json={"claims": []})
    assert resp.json()["response_state"] == "DRAFT_BLOCKED"


def test_verify_endpoint_deterministic(client, case_with_gap):
    payload = {"claims": [{"claim_id": "C1", "text": "Delivery confirmed.", "claim_type": "fact", "evidence_ids": ["EVD-DSP-000001-01"], "source_ids": []}]}
    first = client.post("/cases/DSP-000001/verify", json=payload).json()
    second = client.post("/cases/DSP-000001/verify", json=payload).json()
    assert first["claim_verifications"] == second["claim_verifications"]


# ---------------------------------------------------------------------------
# Regression: Phase 1-3 endpoints unaffected
# ---------------------------------------------------------------------------


def test_cases_endpoint_still_works(client, case_with_gap):
    assert client.get("/cases").status_code == 200


def test_score_endpoint_still_works(client, case_with_gap, risk_model):
    assert client.post("/cases/DSP-000001/score").status_code == 200


def test_decision_endpoint_still_works(client, case_with_gap, risk_model):
    assert client.post("/cases/DSP-000001/decision").status_code == 200
