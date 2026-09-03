"""Phase 8 -- the full generation failure matrix, end to end.

Covers every way generation can fail and asserts the system distinguishes
them WITHOUT weakening anything: response_state keeps its Phase 4 meaning,
and the additive `generation_error_kind` says whether no draft exists
because the provider was unusable or because it returned invalid output.

The key property under test: a provider outage must never be presented as
"the verifier rejected this draft", and a verifier rejection must never be
presented as an outage. Both still refuse to produce a usable draft.

No test here makes a real network call -- OpenRouter behaviour is exercised
through httpx.MockTransport, and the pipeline through FakeLLMProvider.
"""

import json

import httpx
import pytest

from app.api.drafts import get_optional_llm_provider
from app.evidence_intel.generation import (
    InvalidOutputError,
    LLMOutputError,
    ProviderUnavailableError,
)
from app.evidence_intel.llm_provider import (
    FakeLLMProvider,
    LLMGenerationError,
    OpenRouterLLMProvider,
)
from app.main import app
from tests.factories import add_evidence, make_case

pytest.importorskip("lightgbm")
pytest.importorskip("shap")

FREE_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
BASE_URL = "https://openrouter.ai/api/v1"


@pytest.fixture()
def case_with_gap(db_session):
    dispute = make_case(db_session, dispute_id="DSP-000077", reason_code="goods_not_received")
    add_evidence(
        db_session, dispute, evidence_type="proof_of_delivery", available=False, value=None,
        relevance="high", strength=0.0, evidence_id="EVD-POD-077",
    )
    return dispute


@pytest.fixture(autouse=True)
def _clear_llm_override():
    yield
    app.dependency_overrides.pop(get_optional_llm_provider, None)


def _provider(handler) -> OpenRouterLLMProvider:
    return OpenRouterLLMProvider(
        api_key="sk-or-fake", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler)
    )


def _tool_response(arguments: str, tool_name: str = "emit_grounded_draft") -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [
            {"function": {"name": tool_name, "arguments": arguments}}
        ]}}]},
    )


VALID_DRAFT = {
    "summary": "Delivery is documented.",
    "claims": [
        {
            "claim_id": "C1",
            "text": "Delivery was confirmed.",
            "claim_type": "fact",
            "evidence_ids": [],
            "source_ids": ["stripe_dispute_reason_codes_2026"],
        }
    ],
    "missing_evidence": ["proof_of_delivery"],
    "response_body": "Delivery was confirmed.",
}


# ---------------------------------------------------------------------------
# 1. Successful generation (provider level)
# ---------------------------------------------------------------------------


def test_1_successful_generation_returns_parsed_arguments():
    provider = _provider(lambda request: _tool_response(json.dumps(VALID_DRAFT)))
    result = provider.complete_structured(system="s", user="u", schema={}, tool_name="emit_grounded_draft")
    assert result == VALID_DRAFT
    provider.close()


# ---------------------------------------------------------------------------
# 2-6. Provider-level failures -- all refuse, none fabricate
# ---------------------------------------------------------------------------


def test_2_malformed_tool_call_json_is_rejected():
    provider = _provider(lambda request: _tool_response("{not valid json"))
    with pytest.raises(LLMGenerationError, match="not valid JSON"):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit_grounded_draft")
    provider.close()


def test_3_missing_tool_call_is_rejected_and_reports_finish_reason():
    def handler(request):
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "Here is my answer."}}]}
        )

    provider = _provider(handler)
    with pytest.raises(LLMGenerationError, match="tool_calls"):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit_grounded_draft")
    provider.close()


def test_4_non_object_tool_arguments_are_rejected():
    provider = _provider(lambda request: _tool_response("[1, 2, 3]"))
    with pytest.raises(LLMGenerationError, match="JSON object"):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit_grounded_draft")
    provider.close()


def test_5_http_5xx_is_rejected():
    provider = _provider(lambda request: httpx.Response(503, text="service unavailable"))
    with pytest.raises(LLMGenerationError, match="503"):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit_grounded_draft")
    provider.close()


def test_5b_rate_limit_is_rejected_cleanly():
    """The live failure mode for the Google free endpoints: HTTP 429."""

    def handler(request):
        return httpx.Response(429, json={"error": {"code": 429, "message": "temporarily rate-limited upstream"}})

    provider = _provider(handler)
    with pytest.raises(LLMGenerationError, match="429"):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit_grounded_draft")
    provider.close()


def test_5c_upstream_error_in_a_200_envelope_is_rejected():
    """The live failure mode for the Nvidia free endpoint: an upstream error
    wrapped in HTTP 200 with no `choices` at all."""

    def handler(request):
        return httpx.Response(
            200, json={"id": "gen-1", "error": {"message": "Upstream error from Nvidia: overloaded", "code": 502}}
        )

    provider = _provider(handler)
    with pytest.raises(LLMGenerationError, match="overloaded"):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit_grounded_draft")
    provider.close()


def test_6_timeout_is_rejected():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    provider = _provider(handler)
    with pytest.raises(LLMGenerationError):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit_grounded_draft")
    provider.close()


# ---------------------------------------------------------------------------
# 7. Missing API key -> no provider, not a crash
# ---------------------------------------------------------------------------


def test_7_missing_api_key_yields_no_provider(monkeypatch):
    from app.config import get_settings
    from app.evidence_intel.llm_provider import get_llm_provider

    for var in ("LLM_PROVIDER", "LLM_MODEL", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    get_settings.cache_clear()
    try:
        assert get_llm_provider() is None
    finally:
        get_settings.cache_clear()


def test_7b_endpoint_reports_generation_unavailable_without_a_provider(client, case_with_gap, risk_model):
    app.dependency_overrides[get_optional_llm_provider] = lambda: None
    body = client.post("/cases/DSP-000077/draft").json()

    assert body["response_state"] == "GENERATION_UNAVAILABLE"
    assert body["generation_available"] is False
    assert body["response_body"] is None
    assert body["generation_error_kind"] is None  # nothing was attempted
    # the deterministic half of the pipeline is still fully returned
    assert body["evidence_gap"]["coverage"]["required"] > 0
    assert len(body["retrieved_sources"]) > 0


# ---------------------------------------------------------------------------
# Error classification: outage vs invalid output vs verifier rejection
# ---------------------------------------------------------------------------


def test_provider_failure_is_classified_as_provider_unavailable(client, case_with_gap, risk_model):
    app.dependency_overrides[get_optional_llm_provider] = lambda: FakeLLMProvider(raise_error=True)
    body = client.post("/cases/DSP-000077/draft").json()

    assert body["response_state"] == "DRAFT_BLOCKED"  # Phase 4 contract unchanged
    assert body["generation_error_kind"] == "provider_unavailable"
    assert body["claim_verifications"] == []  # nothing was verified, because nothing was drafted


def test_schema_violation_is_classified_as_invalid_output(client, case_with_gap, risk_model):
    """The provider responded, but with something that is not a draft."""
    app.dependency_overrides[get_optional_llm_provider] = lambda: FakeLLMProvider(
        response={"summary": "s"}  # missing claims / response_body
    )
    body = client.post("/cases/DSP-000077/draft").json()

    assert body["response_state"] == "DRAFT_BLOCKED"
    assert body["generation_error_kind"] == "invalid_output"


def test_error_subclasses_remain_catchable_as_llm_output_error():
    """Backward compatibility: existing handlers catch the parent type."""
    assert issubclass(ProviderUnavailableError, LLMOutputError)
    assert issubclass(InvalidOutputError, LLMOutputError)


# ---------------------------------------------------------------------------
# 8-11. Verifier behaviour is unchanged and remains authoritative
# ---------------------------------------------------------------------------


def test_8_unsupported_claim_blocks_the_draft(client, case_with_gap, risk_model):
    app.dependency_overrides[get_optional_llm_provider] = lambda: FakeLLMProvider(
        response={
            "summary": "s",
            "claims": [
                {
                    "claim_id": "C1",
                    "text": "Proof of delivery is on file.",
                    "claim_type": "fact",
                    "evidence_ids": ["EVD-DOES-NOT-EXIST"],
                    "source_ids": [],
                }
            ],
            "missing_evidence": [],
            "response_body": "Proof of delivery is on file.",
        }
    )
    body = client.post("/cases/DSP-000077/draft").json()

    assert body["response_state"] == "DRAFT_BLOCKED"
    # blocked by verification, NOT by a provider problem
    assert body["generation_error_kind"] is None
    statuses = {c["claim_id"]: c["status"] for c in body["claim_verifications"]}
    assert statuses["C1"] in {"UNSUPPORTED", "INVALID_REFERENCE"}


def test_9_missing_evidence_can_be_stated_without_fabricating_an_id(client, case_with_gap, risk_model):
    """A claim may report evidence as genuinely absent -- with no citation,
    because none is possible -- and still verify."""
    app.dependency_overrides[get_optional_llm_provider] = lambda: FakeLLMProvider(
        response={
            "summary": "s",
            "claims": [
                {
                    "claim_id": "C1",
                    "text": "Proof of delivery is not on file for this transaction.",
                    "claim_type": "fact",
                    "evidence_ids": [],
                    "source_ids": [],
                }
            ],
            "missing_evidence": ["proof_of_delivery"],
            "response_body": "Proof of delivery is not on file for this transaction.",
        }
    )
    body = client.post("/cases/DSP-000077/draft").json()

    assert body["missing_evidence"] == ["proof_of_delivery"]
    statuses = {c["claim_id"]: c["status"] for c in body["claim_verifications"]}
    assert statuses["C1"] == "SUPPORTED"


def test_10_one_unsupported_claim_blocks_the_whole_draft(client, case_with_gap, risk_model):
    """Even with a majority of good claims, one bad claim blocks everything."""
    app.dependency_overrides[get_optional_llm_provider] = lambda: FakeLLMProvider(
        response={
            "summary": "s",
            "claims": [
                {
                    "claim_id": "C1",
                    "text": "Delivery was confirmed.",
                    "claim_type": "fact",
                    "evidence_ids": [],
                    "source_ids": ["stripe_dispute_reason_codes_2026"],
                },
                {
                    "claim_id": "C2",
                    "text": "A signed receipt is on file.",
                    "claim_type": "fact",
                    "evidence_ids": ["EVD-FABRICATED"],
                    "source_ids": [],
                },
            ],
            "missing_evidence": [],
            "response_body": "Delivery was confirmed. A signed receipt is on file.",
        }
    )
    body = client.post("/cases/DSP-000077/draft").json()

    assert body["response_state"] == "DRAFT_BLOCKED"
    statuses = {c["claim_id"]: c["status"] for c in body["claim_verifications"]}
    assert statuses["C1"] == "SUPPORTED"
    assert statuses["C2"] in {"UNSUPPORTED", "INVALID_REFERENCE"}


def test_11_fully_supported_draft_is_ready(client, case_with_gap, risk_model):
    app.dependency_overrides[get_optional_llm_provider] = lambda: FakeLLMProvider(response=VALID_DRAFT)
    body = client.post("/cases/DSP-000077/draft").json()

    assert body["response_state"] == "DRAFT_READY"
    assert body["generation_error_kind"] is None
    assert body["response_body"] == "Delivery was confirmed."
    assert {c["claim_id"] for c in body["claim_verifications"]} == {"C1", "RESPONSE_BODY"}
    assert all(c["status"] == "SUPPORTED" for c in body["claim_verifications"])
    assert body["verifier_version"] == "verifier-v1.1"
    assert body["prompt_version"] == "prompt-v1.1"


# ---------------------------------------------------------------------------
# Configuration safety
# ---------------------------------------------------------------------------


def test_configured_model_is_pinned_and_free():
    """No router alias, no paid model: the configured model must name one
    exact free endpoint."""
    from app.config import Settings

    model = Settings(_env_file=None).llm_model
    assert model.endswith(":free")
    assert model != "openrouter/free"
    assert "/" in model  # a concrete vendor/model id, not a router


def test_provider_refuses_to_construct_a_non_free_model():
    with pytest.raises(ValueError, match=":free"):
        OpenRouterLLMProvider(api_key="k", model="openai/gpt-5", base_url=BASE_URL)


def test_no_retry_on_failure():
    """One failed generation is exactly one HTTP request."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, text="rate limited")

    provider = _provider(handler)
    with pytest.raises(LLMGenerationError):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit_grounded_draft")
    assert calls["n"] == 1
    provider.close()
