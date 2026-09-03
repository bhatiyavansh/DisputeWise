"""Part J -- LLM provider abstraction.

Exactly two places in the codebase talk to a vendor: `anthropic` (imported
lazily inside AnthropicLLMProvider) and raw HTTP via `httpx` (already a
project dependency -- no new SDK added) for OpenRouter's OpenAI-compatible
REST API. Everything downstream (prompt.py, generation.py) talks to the
small `LLMProvider` interface below, never to a vendor directly -- swapping
providers, or adding a third one, never touches generation logic.

Provider selection is env-driven (`LLM_PROVIDER`, default "openrouter" for
this buildathon demo -- see app/config.py). The app is fully functional with
no provider configured at all: `get_llm_provider()` returns `None` rather
than raising, and callers (see generation.py / evidence_intel_service.py)
treat that as the well-defined GENERATION_UNAVAILABLE state, not an error.
No test in this codebase calls a real provider -- see FakeLLMProvider below
and tests/test_llm_provider.py.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from app.config import get_settings


class LLMGenerationError(RuntimeError):
    """The provider was called but failed to produce usable structured output.

    Covers network failure, non-2xx responses, and malformed/missing tool-call
    output alike -- callers (generation.py) never distinguish these; all of
    them mean "no usable draft was produced," and none of them are retried
    here (see OpenRouterLLMProvider's docstring on why: an automatic retry
    could quietly burn a free-tier daily quota).
    """


class LLMProvider(ABC):
    """Structured-output-only interface. No free-text chat completion is
    exposed on purpose -- Phase 4 never lets the model produce unstructured
    prose that would bypass claim-level verification."""

    name: str

    @abstractmethod
    def complete_structured(self, *, system: str, user: str, schema: dict[str, Any], tool_name: str) -> dict[str, Any]:
        """Return a dict matching `schema` (a JSON-schema `object` description).

        Raises LLMGenerationError if the provider fails or returns something
        that cannot be parsed as the requested structure. Never returns a
        partially-parsed or best-effort result -- malformed output is always
        rejected here, before it can reach generation.py's Pydantic
        validation, the verifier, or the API response.
        """
        raise NotImplementedError


class AnthropicLLMProvider(LLMProvider):
    """Uses forced tool-use to get schema-conformant structured output --
    the reliable way to get JSON out of a Claude model, rather than asking
    for JSON in prose and hoping it parses.

    Not used for the DisputeWise buildathon demo (OpenRouterLLMProvider is
    the default -- see LLM_PROVIDER in app/config.py) but kept fully
    implemented so the provider architecture stays genuinely provider-
    agnostic rather than OpenRouter-specific.
    """

    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic  # imported lazily so the package is only required when actually used

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete_structured(self, *, system: str, user: str, schema: dict[str, Any], tool_name: str) -> dict[str, Any]:
        import anthropic

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=2000,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[
                    {
                        "name": tool_name,
                        "description": "Emit the structured, evidence-grounded dispute-response draft.",
                        "input_schema": schema,
                    }
                ],
                tool_choice={"type": "tool", "name": tool_name},
            )
        except anthropic.APIError as exc:
            raise LLMGenerationError(f"Anthropic API call failed: {exc}") from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                return block.input

        raise LLMGenerationError("Anthropic response did not contain the expected tool_use block")


class OpenRouterLLMProvider(LLMProvider):
    """OpenRouter's OpenAI-compatible Chat Completions API, called with
    forced tool-choice for the same reason as AnthropicLLMProvider: asking
    for JSON in prose and hoping it parses is not reliable structured output.

    Free-tier safety (see docs/phase4.md "OpenRouter setup"):
      - Refuses to construct at all unless `model` ends in ":free" -- a
        misconfigured paid model string fails loudly at startup rather than
        silently being called.
      - The request body names exactly one `model` string; OpenRouter's
        multi-model fallback/routing features are never used, so a request
        can never silently land on a different (possibly paid) model.
      - No retry logic anywhere in this class. A failed request raises
        LLMGenerationError once; the caller (generation.py) does not retry
        either. An automatic retry loop is exactly what could exhaust a free
        model's daily request quota, so there isn't one.
      - Error messages are built from the response body/status only, never
        from the request object -- the Authorization header (bearing the API
        key) is never included in an exception message or logged anywhere.
    """

    name = "openrouter"

    DEFAULT_TIMEOUT_SECONDS = 60.0

    def __init__(self, api_key: str, model: str, base_url: str, *, transport: Any = None) -> None:
        """`transport` is a test-only seam (an httpx.BaseTransport, e.g.
        httpx.MockTransport) so tests can exercise real request/response
        handling without any network call or a real API key. Production code
        never passes it -- omitting it uses httpx's normal network transport.
        """
        if not model.endswith(":free"):
            raise ValueError(
                f"OpenRouterLLMProvider only calls explicitly free models, but LLM_MODEL='{model}' does not "
                "end in ':free'. Refusing to construct the provider rather than risk a paid call."
            )

        import httpx

        self._model = model
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.DEFAULT_TIMEOUT_SECONDS,
            transport=transport,
        )

    def complete_structured(self, *, system: str, user: str, schema: dict[str, Any], tool_name: str) -> dict[str, Any]:
        import httpx

        payload = {
            "model": self._model,  # exactly the configured free model -- no fallback list, ever
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": "Emit the structured, evidence-grounded dispute-response draft.",
                        "parameters": schema,
                    },
                }
            ],
            # Force exactly this one tool call, OpenAI-compatible shape --
            # verified against OpenRouter's current tool-calling docs for
            # this model rather than assumed.
            "tool_choice": {"type": "function", "function": {"name": tool_name}},
            "parallel_tool_calls": False,
            "temperature": 0,
            # The configured model is a "reasoning" model that spends a
            # large, variable number of tokens on an internal reasoning
            # trace before emitting the tool call (observed: ~2.7k reasoning
            # tokens for a single real case). Without an explicit budget the
            # response can be truncated mid-reasoning, before the tool_calls
            # block is ever emitted -- which surfaces downstream as "did not
            # contain a tool_calls block" even though the request/tool setup
            # was correct. This headroom exists to make that truncation rare,
            # not to change what gets generated.
            "max_tokens": 8000,
        }

        try:
            response = self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            # Network failure / timeout / connection refused -- "provider
            # unavailable", not retried (see class docstring).
            raise LLMGenerationError(f"OpenRouter request failed: {type(exc).__name__} (provider unreachable)") from exc

        body: dict[str, Any] | None
        try:
            body = response.json()
        except ValueError:
            body = None

        self._log_diagnostics(status_code=response.status_code, body=body)

        if response.status_code != 200:
            raise LLMGenerationError(
                f"OpenRouter request failed with HTTP {response.status_code}: {self._safe_error_text(response)}"
            )

        if body is None:
            raise LLMGenerationError("OpenRouter returned a response that was not valid JSON")

        # OpenRouter can report an upstream-provider failure (rate limit,
        # overload, etc.) as HTTP 200 with an `error` envelope instead of a
        # non-200 status -- observed live: {"error": {"message": "Upstream
        # error from Nvidia: Service temporarily overloaded", "code": 502}}
        # with no `choices` at all. Left unchecked this fell through to the
        # generic "did not contain a tool_calls block" message, which is
        # true but hides the actual, more useful cause. Checked before
        # touching `choices` so the real reason surfaces in
        # response_state_reason.
        if isinstance(body.get("error"), dict):
            error = body["error"]
            message = error.get("message", "unknown error")
            code = error.get("code")
            raise LLMGenerationError(f"OpenRouter reported an upstream error: {message} (code={code!r})")

        return self._extract_tool_arguments(body, tool_name)

    @staticmethod
    def _log_diagnostics(*, status_code: int, body: dict[str, Any] | None) -> None:
        """Development-only, structure-only diagnostics for a tool-calling
        failure -- never the request (no prompt/case content) and never the
        Authorization header/API key. Silent in production (ENVIRONMENT=production).
        """
        if get_settings().environment == "production":
            return

        if body is None:
            print(f"[DisputeWise][openrouter] status={status_code} body=<not valid JSON>")  # noqa: T201
            return

        try:
            choices = body.get("choices")
            choice = choices[0] if isinstance(choices, list) and choices else {}
            message = choice.get("message") if isinstance(choice, dict) else {}
            message = message if isinstance(message, dict) else {}
            tool_calls = message.get("tool_calls")
            print(  # noqa: T201
                "[DisputeWise][openrouter] "
                f"status={status_code} model={body.get('model')!r} "
                f"finish_reason={choice.get('finish_reason')!r} "
                f"native_finish_reason={choice.get('native_finish_reason')!r} "
                f"message_keys={sorted(message.keys())} "
                f"has_tool_calls={tool_calls is not None} "
                f"tool_call_count={len(tool_calls) if isinstance(tool_calls, list) else 0} "
                f"refusal_present={message.get('refusal') is not None} "
                f"content_present={bool(message.get('content'))} "
                f"provider={body.get('provider')!r}"
            )
        except Exception as exc:  # diagnostics must never break the real request path
            print(f"[DisputeWise][openrouter] status={status_code} (failed to introspect response shape: {exc})")  # noqa: T201

    @staticmethod
    def _safe_error_text(response: Any, limit: int = 500) -> str:
        """Response body only -- never the request (which carries the
        Authorization header) -- and truncated so a huge error page can't
        blow up a log line."""
        try:
            text = response.text
        except Exception:
            return "<unreadable response body>"
        return text[:limit]

    @staticmethod
    def _extract_tool_arguments(body: dict[str, Any], tool_name: str) -> dict[str, Any]:
        # Structured output only comes through `tool_calls` -- we never fall
        # back to parsing `message.content` as JSON here, even if it happens
        # to look structured. That would mean trusting arbitrary prose as
        # validated output, which is exactly what forced tool-calling exists
        # to avoid (see class docstring and generation.py).
        try:
            tool_calls = body["choices"][0]["message"]["tool_calls"]
        except (KeyError, IndexError, TypeError) as exc:
            finish_reason = None
            try:
                finish_reason = body["choices"][0].get("finish_reason")
            except (KeyError, IndexError, TypeError):
                pass
            raise LLMGenerationError(
                f"OpenRouter response did not contain a tool_calls block (finish_reason={finish_reason!r})"
            ) from exc

        if not tool_calls:
            raise LLMGenerationError("OpenRouter response contained an empty tool_calls list")

        matching = [c for c in tool_calls if isinstance(c, dict) and c.get("function", {}).get("name") == tool_name]
        call = matching[0] if matching else tool_calls[0]

        arguments_raw = call.get("function", {}).get("arguments") if isinstance(call, dict) else None
        if not isinstance(arguments_raw, str):
            raise LLMGenerationError("OpenRouter tool call 'arguments' field was missing or not a string")

        try:
            parsed = json.loads(arguments_raw)
        except json.JSONDecodeError as exc:
            raise LLMGenerationError(f"OpenRouter tool call arguments were not valid JSON: {exc}") from exc

        if not isinstance(parsed, dict):
            raise LLMGenerationError("OpenRouter tool call arguments did not decode to a JSON object")

        return parsed

    def close(self) -> None:
        self._client.close()


class FakeLLMProvider(LLMProvider):
    """Test double: returns a pre-programmed structured payload (or raises),
    without any network call. Lives here (not just in tests/) because it is
    a legitimate, documented part of the provider architecture -- Part J
    explicitly requires the app to be testable without a real LLM. This is
    the ONLY provider any automated test in this codebase uses."""

    name = "fake"

    def __init__(self, response: dict[str, Any] | None = None, *, raise_error: bool = False) -> None:
        self._response = response
        self._raise_error = raise_error
        self.calls: list[dict[str, Any]] = []

    def complete_structured(self, *, system: str, user: str, schema: dict[str, Any], tool_name: str) -> dict[str, Any]:
        self.calls.append({"system": system, "user": user, "schema": schema, "tool_name": tool_name})
        if self._raise_error or self._response is None:
            raise LLMGenerationError("FakeLLMProvider configured to fail")
        return json.loads(json.dumps(self._response))  # deep copy, deterministic


def get_llm_provider() -> LLMProvider | None:
    """Returns None (not an error) whenever no usable provider is configured:
    unset API key for the selected provider, an unrecognized LLM_PROVIDER
    value, or (OpenRouter only) a configured model that fails the ":free"
    safety check. Callers must treat None as GENERATION_UNAVAILABLE, per
    Part J -- this function itself never raises.
    """
    settings = get_settings()
    provider_name = (settings.llm_provider or "").strip().lower()

    if provider_name == "openrouter":
        if not settings.openrouter_api_key:
            return None
        try:
            return OpenRouterLLMProvider(
                api_key=settings.openrouter_api_key,
                model=settings.llm_model,
                base_url=settings.openrouter_base_url,
            )
        except ValueError as exc:
            # Misconfigured (non-free) model -- fail safe to "unavailable"
            # rather than raise out of a FastAPI dependency, but still surface
            # it somewhere an operator would see it during a demo.
            print(f"[DisputeWise] OpenRouter provider not started: {exc}")  # noqa: T201
            return None

    if provider_name == "anthropic":
        if not settings.anthropic_api_key:
            return None
        return AnthropicLLMProvider(api_key=settings.anthropic_api_key, model=settings.llm_model)

    return None
