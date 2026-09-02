"""Part J -- LLM provider abstraction tests.

No test here makes a real network call to any provider or requires an API
key -- that is the entire point of the abstraction. OpenRouterLLMProvider's
HTTP behavior is exercised against httpx.MockTransport (a fake in-process
transport, not a real socket); AnthropicLLMProvider's construction is
exercised with a fake key (it never calls out during __init__). Neither
provider's complete_structured() is ever invoked against a real API here.
"""

import json

import httpx
import pytest

from app.evidence_intel.llm_provider import (
    AnthropicLLMProvider,
    FakeLLMProvider,
    LLMGenerationError,
    OpenRouterLLMProvider,
    get_llm_provider,
)

FREE_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
BASE_URL = "https://openrouter.ai/api/v1"


def _clear_llm_env(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_MODEL", "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# get_llm_provider() factory / configuration
# ---------------------------------------------------------------------------


def test_get_llm_provider_returns_none_when_openrouter_key_unconfigured(monkeypatch):
    from app.config import get_settings

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    get_settings.cache_clear()
    try:
        assert get_llm_provider() is None
    finally:
        get_settings.cache_clear()


def test_get_llm_provider_returns_openrouter_provider_when_configured(monkeypatch):
    from app.config import get_settings

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-fake-key-not-real")
    monkeypatch.setenv("LLM_MODEL", FREE_MODEL)
    get_settings.cache_clear()
    try:
        provider = get_llm_provider()
        assert provider is not None
        assert provider.name == "openrouter"
    finally:
        _clear_llm_env(monkeypatch)
        get_settings.cache_clear()


def test_get_llm_provider_returns_none_for_unrecognized_provider_name(monkeypatch):
    from app.config import get_settings

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "some_unknown_provider")
    get_settings.cache_clear()
    try:
        assert get_llm_provider() is None
    finally:
        get_settings.cache_clear()


def test_get_llm_provider_returns_none_rather_than_raising_for_paid_model(monkeypatch):
    """A misconfigured (non-free) model must degrade to 'unavailable', not crash the app."""
    from app.config import get_settings

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-fake-key-not-real")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-5")  # deliberately not ":free"
    get_settings.cache_clear()
    try:
        assert get_llm_provider() is None
    finally:
        _clear_llm_env(monkeypatch)
        get_settings.cache_clear()


def test_get_llm_provider_returns_anthropic_when_explicitly_selected(monkeypatch):
    from app.config import get_settings

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-not-real")
    get_settings.cache_clear()
    try:
        provider = get_llm_provider()
        assert provider is not None
        assert provider.name == "anthropic"
    finally:
        _clear_llm_env(monkeypatch)
        get_settings.cache_clear()


def test_get_llm_provider_default_is_openrouter_not_anthropic(monkeypatch):
    """Product decision: OpenRouter is the demo default; Anthropic must be
    explicitly selected via LLM_PROVIDER, never used implicitly. Clears the
    real process env too (docker-compose.yml sets LLM_PROVIDER as a container
    env var, so `_env_file=None` alone wouldn't isolate this test from it)."""
    from app.config import Settings

    _clear_llm_env(monkeypatch)
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "openrouter"
    assert settings.llm_model == "nvidia/nemotron-3-super-120b-a12b:free"


# ---------------------------------------------------------------------------
# OpenRouterLLMProvider -- construction / free-tier safety
# ---------------------------------------------------------------------------


def test_openrouter_provider_construction_does_not_call_the_network():
    provider = OpenRouterLLMProvider(api_key="sk-or-fake", model=FREE_MODEL, base_url=BASE_URL)
    assert provider.name == "openrouter"
    provider.close()


def test_openrouter_provider_rejects_non_free_model():
    with pytest.raises(ValueError, match=":free"):
        OpenRouterLLMProvider(api_key="sk-or-fake", model="openai/gpt-5", base_url=BASE_URL)


def test_openrouter_provider_base_url_is_configurable():
    provider = OpenRouterLLMProvider(
        api_key="sk-or-fake", model=FREE_MODEL, base_url="https://custom.example.com/v1/"
    )
    assert str(provider._client.base_url) == "https://custom.example.com/v1/"
    provider.close()


def test_openrouter_provider_model_is_configurable_to_any_free_model():
    provider = OpenRouterLLMProvider(api_key="sk-or-fake", model="google/gemma-4-31b-it:free", base_url=BASE_URL)
    assert provider._model == "google/gemma-4-31b-it:free"
    provider.close()


# ---------------------------------------------------------------------------
# OpenRouterLLMProvider -- request construction (via MockTransport)
# ---------------------------------------------------------------------------


def _tool_call_response(tool_name: str, arguments: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"function": {"name": tool_name, "arguments": json.dumps(arguments)}}
                        ]
                    }
                }
            ]
        },
    )


def test_openrouter_request_targets_configured_model_only():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        return _tool_call_response("emit", {"summary": "ok", "claims": [], "missing_evidence": [], "response_body": "b"})

    provider = OpenRouterLLMProvider(
        api_key="sk-or-secret-value", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler)
    )
    provider.complete_structured(system="sys", user="usr", schema={"type": "object"}, tool_name="emit")

    assert captured["body"]["model"] == FREE_MODEL
    assert "models" not in captured["body"]  # never a fallback list -- exactly one model
    assert captured["url"] == f"{BASE_URL}/chat/completions"
    assert captured["auth"] == "Bearer sk-or-secret-value"
    provider.close()


def test_openrouter_request_forces_tool_choice_to_the_named_tool():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _tool_call_response("emit_grounded_draft", {"summary": "ok", "claims": [], "missing_evidence": [], "response_body": "b"})

    provider = OpenRouterLLMProvider(
        api_key="sk-or-fake", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler)
    )
    provider.complete_structured(system="sys", user="usr", schema={"type": "object"}, tool_name="emit_grounded_draft")

    assert captured["body"]["tool_choice"] == {"type": "function", "function": {"name": "emit_grounded_draft"}}
    assert captured["body"]["tools"][0]["function"]["name"] == "emit_grounded_draft"
    provider.close()


# ---------------------------------------------------------------------------
# OpenRouterLLMProvider -- structured output parsing
# ---------------------------------------------------------------------------


def test_openrouter_parses_valid_tool_call_arguments():
    payload = {"summary": "s", "claims": [{"claim_id": "C1", "text": "t", "claim_type": "fact", "evidence_ids": [], "source_ids": []}], "missing_evidence": [], "response_body": "b"}
    handler = lambda request: _tool_call_response("emit", payload)  # noqa: E731
    provider = OpenRouterLLMProvider(api_key="k", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler))

    result = provider.complete_structured(system="s", user="u", schema={}, tool_name="emit")
    assert result == payload
    provider.close()


def test_openrouter_picks_the_matching_tool_call_when_multiple_present():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {"function": {"name": "some_other_tool", "arguments": "{}"}},
                                {"function": {"name": "emit", "arguments": json.dumps({"summary": "right one", "claims": [], "missing_evidence": [], "response_body": "b"})}},
                            ]
                        }
                    }
                ]
            },
        )

    provider = OpenRouterLLMProvider(api_key="k", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler))
    result = provider.complete_structured(system="s", user="u", schema={}, tool_name="emit")
    assert result["summary"] == "right one"
    provider.close()


# ---------------------------------------------------------------------------
# OpenRouterLLMProvider -- malformed output must be rejected cleanly
# ---------------------------------------------------------------------------


def test_openrouter_rejects_arguments_that_are_not_valid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{"function": {"name": "emit", "arguments": "{not valid json"}}]}}]})

    provider = OpenRouterLLMProvider(api_key="k", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler))
    with pytest.raises(LLMGenerationError, match="not valid JSON"):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit")
    provider.close()


def test_openrouter_rejects_response_with_no_tool_calls():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "I cannot help with that."}}]})

    provider = OpenRouterLLMProvider(api_key="k", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler))
    with pytest.raises(LLMGenerationError, match="tool_calls"):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit")
    provider.close()


def test_openrouter_rejects_empty_tool_calls_list():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"tool_calls": []}}]})

    provider = OpenRouterLLMProvider(api_key="k", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler))
    with pytest.raises(LLMGenerationError):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit")
    provider.close()


def test_openrouter_rejects_non_json_response_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    provider = OpenRouterLLMProvider(api_key="k", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler))
    with pytest.raises(LLMGenerationError, match="not valid JSON"):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit")
    provider.close()


def test_openrouter_rejects_arguments_that_decode_to_a_non_object():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{"function": {"name": "emit", "arguments": "[1, 2, 3]"}}]}}]})

    provider = OpenRouterLLMProvider(api_key="k", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler))
    with pytest.raises(LLMGenerationError, match="JSON object"):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit")
    provider.close()


# ---------------------------------------------------------------------------
# OpenRouterLLMProvider -- provider-unavailable / failure behavior
# ---------------------------------------------------------------------------


def test_openrouter_raises_clean_error_on_non_200_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    provider = OpenRouterLLMProvider(api_key="k", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler))
    with pytest.raises(LLMGenerationError, match="429"):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit")
    provider.close()


def test_openrouter_error_message_never_contains_the_api_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    provider = OpenRouterLLMProvider(
        api_key="sk-or-super-secret-value-12345", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler)
    )
    try:
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit")
        pytest.fail("expected LLMGenerationError")
    except LLMGenerationError as exc:
        assert "sk-or-super-secret-value-12345" not in str(exc)
    provider.close()


def test_openrouter_network_failure_raises_llm_generation_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = OpenRouterLLMProvider(api_key="k", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler))
    with pytest.raises(LLMGenerationError, match="unreachable"):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit")
    provider.close()


def test_openrouter_timeout_raises_llm_generation_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = OpenRouterLLMProvider(api_key="k", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler))
    with pytest.raises(LLMGenerationError):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit")
    provider.close()


def test_openrouter_does_not_retry_on_failure():
    """No automatic retry loop -- a single failed call is one HTTP request, not more."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(503, text="service unavailable")

    provider = OpenRouterLLMProvider(api_key="k", model=FREE_MODEL, base_url=BASE_URL, transport=httpx.MockTransport(handler))
    with pytest.raises(LLMGenerationError):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="emit")
    assert call_count["n"] == 1
    provider.close()


# ---------------------------------------------------------------------------
# AnthropicLLMProvider -- unchanged, still available, not the default
# ---------------------------------------------------------------------------


def test_anthropic_provider_construction_does_not_call_the_network():
    provider = AnthropicLLMProvider(api_key="sk-test-fake-key-not-real", model="claude-sonnet-5")
    assert provider.name == "anthropic"


# ---------------------------------------------------------------------------
# FakeLLMProvider -- the only provider automated tests actually invoke
# ---------------------------------------------------------------------------


def test_fake_provider_returns_configured_response():
    payload = {"summary": "s", "claims": [], "missing_evidence": [], "response_body": "body"}
    provider = FakeLLMProvider(response=payload)
    result = provider.complete_structured(system="sys", user="usr", schema={}, tool_name="t")
    assert result == payload


def test_fake_provider_records_calls():
    provider = FakeLLMProvider(response={"summary": "s", "claims": [], "missing_evidence": [], "response_body": "b"})
    provider.complete_structured(system="SYS", user="USR", schema={"a": 1}, tool_name="t")
    assert len(provider.calls) == 1
    assert provider.calls[0]["system"] == "SYS"
    assert provider.calls[0]["user"] == "USR"


def test_fake_provider_returns_deep_copy_not_shared_reference():
    payload = {"summary": "s", "claims": [], "missing_evidence": [], "response_body": "b"}
    provider = FakeLLMProvider(response=payload)
    result = provider.complete_structured(system="s", user="u", schema={}, tool_name="t")
    result["summary"] = "mutated"
    assert payload["summary"] == "s"  # original untouched


def test_fake_provider_can_simulate_failure():
    provider = FakeLLMProvider(raise_error=True)
    with pytest.raises(LLMGenerationError):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="t")


def test_fake_provider_with_no_response_configured_raises():
    provider = FakeLLMProvider()
    with pytest.raises(LLMGenerationError):
        provider.complete_structured(system="s", user="u", schema={}, tool_name="t")
