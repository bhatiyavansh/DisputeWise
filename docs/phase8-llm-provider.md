# Phase 8 — Free LLM provider evaluation

## Decision: stay on `nvidia/nemotron-3-super-120b-a12b:free`

The plan was to switch generation to `google/gemma-4-26b-a4b-it:free`, conditional on that free endpoint actually being available. **It is not**, so the model was not switched.

### Evidence

`scripts/probe_llm_models.py` checks the three things that must all hold: genuinely free pricing, advertised tool-calling support, and whether the endpoint is actually serving requests. Re-run it any time:

```bash
docker compose cp scripts/probe_llm_models.py backend:/tmp/probe_llm_models.py
docker compose exec backend python3 /tmp/probe_llm_models.py --attempts 3
```

Result (2026-09-04):

| Model | Free (0/0) | Advertises tools | Live tool calls | Verdict |
|---|---|---|---|---|
| `nvidia/nemotron-3-super-120b-a12b:free` | yes | yes | **3/3** | USABLE |
| `google/gemma-4-26b-a4b-it:free` | yes | yes | **0/3** — HTTP 429 | NOT USABLE |
| `google/gemma-4-31b-it:free` | yes | yes | **0/3** — HTTP 429 | NOT USABLE |

```
google/gemma-4-26b-a4b-it:free is temporarily rate-limited upstream.
Please retry shortly, or add your own key to accumulate your rate limits
(provider: Google AI Studio)
```

Across ~5 minutes and 15 spaced attempts, every Gemma request failed with HTTP 429 — **including a trivial request with no `tools` at all.** So this is an availability limit on the Google AI Studio free tier for this account, not a tool-calling incompatibility. Both Google free endpoints behave identically, which points at a provider-level cap rather than a per-model issue.

The instruction was explicit: switch *only if* the free model is currently available, never pay, never add credits, never use the `openrouter/free` router (non-deterministic model routing). Nemotron is pinned, exact, free, and currently returns forced tool calls reliably. Switching to a model that returns 429 to every request would have made generation permanently unavailable.

**If Gemma's free tier frees up**, switching is a one-line config change and needs no code: set `LLM_MODEL=google/gemma-4-26b-a4b-it:free`. Re-run the probe first.

## What actually changed

The two known failure modes are now distinguishable, without touching the state machine, the verifier, or the prompt.

Both live free endpoints fail in *different* ways, and neither is a plain HTTP error:

- **Nvidia**: HTTP **200** carrying an `{"error": {...}}` envelope with no `choices` (handled since the previous hardening pass).
- **Google**: HTTP **429** with a rate-limit envelope.

Previously *every* generation failure — provider outage, malformed output, or a verifier rejection — surfaced as `DRAFT_BLOCKED`. That conflated two very different situations: "the verifier caught an unsupported claim" and "the model was never reachable, so nothing was ever written to verify". The UI blamed the verifier for outages.

Added, additively:

- `ProviderUnavailableError` and `InvalidOutputError`, both **subclasses of `LLMOutputError`** — every existing `except LLMOutputError` and `pytest.raises(LLMOutputError)` still catches them, so no existing behaviour changed.
- `generation_error_kind` on the draft response: `"provider_unavailable"`, `"invalid_output"`, or `null`.

**`response_state` keeps its exact Phase 4 meaning.** A generation failure is still `DRAFT_BLOCKED`; the new field only explains *why* no draft exists. Nothing was weakened: absent tool calls are still a hard failure, `content` is still never parsed as a fallback, malformed output is still rejected before Pydantic, and the verifier is untouched at `verifier-v1.1`.

The UI now reads:

| Situation | Shown as |
|---|---|
| Verified draft | Draft ready |
| Verifier rejected a claim | **Draft blocked by verifier** |
| Provider unreachable / rate-limited / no tool call | **AI generation temporarily unavailable** |
| Provider returned unparseable output | **AI generation returned unusable output** |
| No provider configured | AI generation unavailable |
| Backend unreachable | (network error state, one level up) |

A provider problem also states that nothing was verified and that scoring, decision, evidence gaps and retrieval are unaffected — the product stays useful when the LLM is not.

## Preserved

`LLMProvider` abstraction · forced `tool_choice` · `parallel_tool_calls: false` · `temperature: 0` · pinned exact `:free` model (never a router alias) · Pydantic validation · `prompt-v1.1` unchanged · `verifier-v1.1` unchanged · **no retries** (one failed generation is exactly one HTTP request, asserted by test) · no paid model, no credits.

## Verification

`backend/tests/test_generation_failure_modes.py` — 20 tests covering the full matrix: successful generation, malformed tool-call JSON, missing tool call, non-object arguments, HTTP 5xx, HTTP 429, the 200-with-error-envelope case, timeout, missing API key, unsupported claim, missing evidence stated without fabricating an ID, one bad claim blocking a whole draft, a fully verified draft, error classification, model pinning, and no-retry.

`frontend/src/components/case/DraftStateBanner.test.tsx` — 6 tests asserting the UI never presents an outage as a verifier rejection (or vice versa) and never implies a usable draft exists in any failure state.

Real end-to-end run against `DSP-031597` (live Nemotron, 39.7s): 12 claims generated, **11 SUPPORTED, 1 UNSUPPORTED, 1 INCOMPLETE** → `DRAFT_BLOCKED` with `generation_error_kind: null` — correctly attributed to the verifier, not the provider.

## Known limitation

Free OpenRouter endpoints are best-effort and rate-limited without warning. Generation can be unavailable at any moment, including during a demo. This is a property of using free inference, not a defect — the system degrades safely: scoring, the decision, evidence-gap analysis and retrieval are all deterministic and unaffected, and the UI says plainly that generation is unavailable rather than showing a fabricated or stale draft.
