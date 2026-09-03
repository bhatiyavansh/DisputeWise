# Phase 4 — Evidence Intelligence, Grounded RAG & Claim-Level Verification

Phase 1 built the data. Phase 2 predicts whether a dispute is winnable. Phase 3 decides whether it's economically worth contesting. Phase 4 answers the question everything before it was building toward: **if we're going to contest, what evidence do we have, what does authoritative guidance say, and can we prove every sentence of the response is actually grounded in that evidence — before a human ever sees it?**

This is deliberately not "an LLM that writes chargeback responses." Razorpay already has dispute-response tooling; that's not the differentiator. The differentiator is the loop: **evidence gap → retrieval → grounded generation → claim-level verification → block-by-default**. A generic RAG chatbot answers questions; this system refuses to hand a merchant a sentence it can't trace back to a specific evidence_id or source_id.

## Architecture

```
dispute (Phase 1)
      │
      ▼
evidence matrix (Phase 1) ──► LightGBM P(win) (Phase 2) ──► economic decision (Phase 3)
      │                                                              │
      ▼                                                              │
EVIDENCE GAP ANALYZER  (app/evidence_intel/gap_analyzer.py)          │
  reason_code + case evidence + data/reference/ → required/available/missing, priority
      │                                                              │
      ▼                                                              │
EVIDENCE PACKET  (app/evidence_intel/packet.py)                      │
  case+transaction+customer facts (narrow) + evidence items + gap + guidance
      │                                                              │
      ▼                                                              │
RAG RETRIEVAL  (app/evidence_intel/knowledge_base.py, retrieval.py)  │
  reason-code filter → TF-IDF rank over data/reference/-derived chunks
      │                                                              │
      ▼                                                              │
GROUNDED GENERATION  (app/evidence_intel/prompt.py, generation.py) ◄─┘  (decision reused, not recomputed)
  strict schema, explicit valid-ID lists, LLMProvider abstraction
      │
      ▼
CLAIM-LEVEL VERIFIER  (app/evidence_intel/verifier.py)
  deterministic per-claim check against the packet -- never the LLM grading itself
      │
      ▼
SAFETY POLICY  (app/evidence_intel/safety.py)
  DRAFT_READY / DRAFT_FLAGGED / DRAFT_BLOCKED
      │
      ▼
HUMAN APPROVAL  (always required -- nothing here submits anything)
```

Every stage is independently callable and independently tested. `service.py`-equivalent orchestration lives in `app/services/evidence_intel_service.py`, following the exact pattern already established by `scoring_service.py` (Phase 2) and `decision_service.py` (Phase 3) — Phase 4 reuses `decide_case()` from Phase 3 for the decision, never recomputes it.

## FACT / REFERENCE / INFERENCE / UNSUPPORTED

Every claim the generator produces is tagged with a `claim_type`, and the distinction is load-bearing, not decorative:

| Type | Meaning | Where it comes from |
|---|---|---|
| **FACT** | Directly present in this case's own evidence | `EvidencePacketItem.claim_type` is always `"fact"` — every evidence row loaded for a case |
| **REFERENCE** | From authoritative reference/guidance, not this case | `ReasonCodeGuidance.claim_type` and retrieved knowledge-base chunks are `"reference"` |
| **INFERENCE** | A conclusion the model drew from FACT + REFERENCE | Must still cite the FACT/REFERENCE it was inferred from — an inference with zero citations is `UNSUPPORTED` (see verifier.py) |
| **UNSUPPORTED** | Not a claim_type the model chooses — it's what the *verifier* assigns when a claim (of any type) can't be traced to real evidence/guidance | Never a label the LLM applies to itself |

**INFERENCE never silently becomes FACT.** The `claim_type` field is preserved end-to-end into the API response and the trace — a frontend can visually distinguish "the delivery was confirmed" (fact) from "this pattern suggests good faith" (inference) rather than presenting both with equal authority.

## Part A — Evidence Gap Analyzer

`app/evidence_intel/gap_analyzer.py`. A pure function of `(reason_code, case_evidence_state)` plus the versioned `data/reference/` tables — no hardcoded per-case logic, no DB access in the core function (a thin wrapper adds that). "Required" evidence = reference-data relevance in `{high, medium}` for that reason code; "low" relevance types are still reported but excluded from the coverage denominator. Priority: `CRITICAL` (missing + high relevance), `IMPORTANT` (missing + medium), `OPTIONAL` (missing + low), `NONE` (available).

Deliberately **broader** than Phase 2/3's own `evidence_summary.missing_key_types`, which only tracks high-relevance gaps: the gap analyzer's `required` set includes medium-relevance types too (for `goods_not_received`: 5 high + 3 medium = 8 required, vs. Phase 2/3's 5). Verified live against `DSP-031597`: Phase 2/3 report only `proof_of_delivery` missing; the gap analyzer additionally finds `refund_request` (medium relevance) missing — a real, more thorough finding, not a bug. Documented here so the discrepancy is never mistaken for one.

Reuses the Phase 1 reference-data strategy exactly as it already exists — no new reference tables, no mixing with ML training data (`scripts/verify_reference_data.py` continues to guard that separation, untouched).

## Part B — Evidence Packet

`app/evidence_intel/packet.py`. **Not a database row dump.** Deliberately excludes: raw `device_id`/`ip_address` (only their derived match booleans are evidence), billing/shipping address IDs, and customer `country` (excluded on the same fairness grounds as Phase 2's feature set). Structurally guarantees no outcome/target field (`favorable_outcome`, `recovery_amount`, `outcome_at`, `outcome_source`) is reachable — the packet builder never receives the `outcomes` table, mirroring Phase 2's leakage guard in `build_features()`. Verified by `test_packet_excludes_raw_pii_fields` / `test_packet_excludes_outcome_fields` and the API-level equivalent.

Every evidence item keeps its real, stable `evidence_id` from the database (`EVD-xxxxxxx`). This one design choice is what makes cross-case contamination and fabricated-ID detection possible later: the verifier's "does this ID exist" check is really "does this ID exist **in this packet**" — an ID that's real for a different case simply isn't in this one.

## Part C — RAG Knowledge Base

`app/evidence_intel/knowledge_base.py`. The entire corpus is **51 chunks**, deterministically built from `data/reference/` (3 reason-code descriptions + 48 evidence-requirement descriptions — one chunk per reason code and one per (reason_code, evidence_type) pair). This does not warrant a vector database, an embedding-model download, or a persisted index: `build_chunks()` reruns in milliseconds from the same CSVs every process start, so "rebuild from versioned reference data" is satisfied by construction rather than a build step. Ranking uses TF-IDF + cosine similarity via scikit-learn — already a Phase 2 dependency, so no new heavy dependency was added for retrieval. `knowledge-v1`.

## Part D — Retrieval

`app/evidence_intel/retrieval.py`. Reason-code metadata filtering happens **before** ranking, not as a post-filter on unrestricted vector search — `KnowledgeBase.search()` narrows to the case's `reason_code` first, then ranks only within that subset. The query text itself is deterministic, not left to an LLM's judgment: `reason_code + " " + missing_evidence_types`, so retrieval is explicitly steered toward the case's actual gaps. Verified live: for `DSP-031597` (goods_not_received, missing `proof_of_delivery`), the top-ranked result is `evidence:goods_not_received:proof_of_delivery` at similarity 0.612 — the single most relevant chunk in the whole corpus, ranked first, exactly because the query construction pulled the gap in.

## Part E — Grounded Response Generation

`app/evidence_intel/prompt.py` + `generation.py`. The model is never asked "write a chargeback response" — it receives the evidence packet, retrieved guidance, and the **exact list of evidence_ids and source_ids it is permitted to cite**, spelled out in the prompt (`prompt.py::build_user_prompt`). Output is forced through the provider's tool-use mechanism (a JSON-schema-typed tool call, not "please respond in JSON") regardless of which `LLMProvider` is active, then validated against a Pydantic model (`GeneratedDraft`) before anything downstream touches it — a provider returning malformed structure is a hard `LLMOutputError`, never silently coerced.

The system prompt (stored verbatim, not chain-of-thought — see Part H) states seven explicit rules: cite only given IDs, never claim unavailable evidence is present, never invent facts, never guarantee an outcome, never assert an ungiven policy requirement, tag every claim's type honestly, and omit anything unsupportable rather than including it. The verifier checks every one of these mechanically — the prompt asking nicely is not the safety mechanism; the code that runs after generation is.

## Part F — Claim-Level Grounding Verifier

`app/evidence_intel/verifier.py` — **the most important file in this phase.** Every claim is checked with deterministic rules against the case's own packet, in this order (first match wins):

1. **INVALID_REFERENCE** — cites an `evidence_id`/`source_id` absent from this case's packet/retrieval entirely. This single check catches three attack surfaces at once: a fabricated ID, a real ID belonging to a *different* case (packets are case-scoped and never merged, so "real for another case" is indistinguishable from "fabricated" here — by design), and a policy citation that was never actually retrieved.
2. **UNSUPPORTED (outcome guarantee)** — regex-detected guarantee language ("guarantee", "certain to win", "100% certain", "assured victory", etc.) — no evidence can support a claim about a future result, so this check runs regardless of what's cited.
3. **UNSUPPORTED (no citation)** — a claim citing nothing at all.
4. **UNSUPPORTED (cites unavailable evidence)** — the ID is real for this case, but the evidence is marked unavailable. Missing evidence cannot become cited proof, full stop.
5. **UNSUPPORTED (fabricated/contradictory date)** — extracts date-like substrings (ISO, slash, and month-name formats) from the claim text and confirms each one appears in the *value* of the evidence cited. A claim that states a date is checked against what its own cited evidence actually says — catches both invented dates and dates that contradict real evidence.
6. **PARTIALLY_SUPPORTED** — every citation is valid and available, but at least one has `strength < 0.3` (`WEAK_EVIDENCE_THRESHOLD`).
7. **SUPPORTED** — otherwise.

**No LLM ever judges its own output here.** All seven checks are string/set operations against the packet's own data — reproducible, inspectable, and (per Part L below) demonstrated against every explicitly-required adversarial scenario.

One documented nuance found while building the evaluation suite (Part K): citing an `evidence_id` in `claims[].evidence_ids` always means *"this grounds my claim"* — even a claim honestly stating evidence is absent must not cite the missing ID that way, or the verifier (correctly) treats it as check #4. Absence is reported through the separate `missing_evidence` field in the response schema instead. This is enforced behavior, not a bug — see `scripts/evaluate_evidence_intel.py`'s comment on evaluation case 2 for the concrete example that surfaced it.

## Part G — Response Safety Policy

`app/evidence_intel/safety.py`. Any single claim in `{UNSUPPORTED, INVALID_REFERENCE}` blocks the **entire** response (`DRAFT_BLOCKED`) — not just that sentence. Rationale: a merchant reading a "mostly grounded" draft has no way to tell which parts to trust unless the system already did that work; partial trust is not a safe default. `PARTIALLY_SUPPORTED` claims (weak evidence, nothing outright wrong) produce `DRAFT_FLAGGED` — usable with review, not blocked. All-`SUPPORTED` is `DRAFT_READY`. A case with zero claims is `DRAFT_BLOCKED` ("nothing to present"). A blocked/flagged draft is never edited, trimmed, or auto-repaired — it's surfaced exactly as generated, with the reasons why.

## Part H — "Why This Response?" Trace

`app/evidence_intel/trace.py`. Every `/draft` response carries a `trace` object: case ID, decision (reused from Phase 3), all eight version strings (`model_version`, `feature_schema_version`, `decision_policy_version`, `evidence_schema_version`, `knowledge_base_version`, `retrieval_config_version`, `prompt_version`, `response_schema_version`, `verifier_version`), retrieved source/chunk IDs, cited evidence IDs, per-status claim counts, final `response_state`, and a UTC timestamp. **No chain-of-thought is stored anywhere** — the system/user prompt text (Part E) already *is* concise structured instruction, and the trace stores only IDs, version strings, and counts, never raw model reasoning.

## Part I — API

Four endpoints, all under the existing `/cases/{case_id}/...` convention, all reusing `app.db.session.get_db` / the existing dependency-injection pattern:

| Endpoint | Purpose |
|---|---|
| `POST /cases/{id}/evidence-gap` | Gap analysis only (Part A) |
| `POST /cases/{id}/evidence-packet` | Full packet (Part B), including embedded gap |
| `POST /cases/{id}/draft` | Full pipeline: decision + gap + packet + retrieval + generation (if available) + verification + safety + trace |
| `POST /cases/{id}/verify` | Independently re-verify a set of claims (e.g. human-edited) against a freshly-rebuilt packet — decoupled from generation on purpose, so the verifier is testable and reusable on its own |

Phase 1–3 contracts are unchanged and regression-tested: `GET /cases`, `GET /cases/{id}`, `GET /cases/{id}/evidence`, `POST /cases/{id}/score`, `POST /cases/{id}/decision` all still behave exactly as before (`tests/test_evidence_intel_api.py`'s regression section, plus the full existing suite passing unmodified).

**`/draft` when no LLM provider is configured** returns HTTP 200 with `response_state: "GENERATION_UNAVAILABLE"` and `generation_available: false` — not a 503, and not an empty response. `decision`, `evidence_gap`, and `retrieved_sources` are still fully populated, because none of those need an LLM. This was a deliberate design decision: a 503 would have hidden real, useful, already-computed data behind an all-or-nothing error, when the frontend (Part P) needs evidence coverage and gaps regardless of whether generation is configured.

## Part J — LLM Provider Architecture

`app/evidence_intel/llm_provider.py`. One interface (`LLMProvider.complete_structured`), three implementations:

- **`OpenRouterLLMProvider`** — the buildathon demo default (`LLM_PROVIDER=openrouter`). Calls OpenRouter's OpenAI-compatible `/chat/completions` endpoint directly via `httpx` (already a project dependency — no new SDK added) with forced tool-choice, exactly the same "don't ask for JSON in prose" principle as the Anthropic path.
- `AnthropicLLMProvider` — uses forced tool-use against the Anthropic Messages API. Kept fully implemented so the architecture stays genuinely provider-agnostic, but **not used for this demo** per explicit product decision — only active if `LLM_PROVIDER=anthropic` is set. The only file in the codebase that imports the `anthropic` SDK.
- `FakeLLMProvider` — a documented, first-class test double (returns a pre-programmed payload or raises, no network call, deep-copies its response so tests can't leak mutation between calls). **The only provider any automated test in this codebase ever invokes.**

`get_llm_provider()` (the factory both `/draft`'s FastAPI dependency and `evidence_intel_service.py` use) reads `LLM_PROVIDER` and dispatches; it returns `None` — never raises — whenever the selected provider has no API key configured, `LLM_PROVIDER` names something unrecognized, or (OpenRouter only) the configured model fails the free-tier safety check below. Callers treat `None` identically to a provider that failed: `GENERATION_UNAVAILABLE`.

### OpenRouter setup (exact instructions)

1. Create a free account at [openrouter.ai](https://openrouter.ai) and generate a key at `openrouter.ai/settings/keys` — no payment method required for free models.
2. Copy `.env.example` to `.env` at the repo root and set `OPENROUTER_API_KEY=<your key>`. Leave `LLM_PROVIDER`, `LLM_MODEL`, and `OPENROUTER_BASE_URL` at their defaults unless you have a specific reason to change them.
3. `docker compose up -d --build` (or just restart the `backend` service if it's already running) so the container picks up the new environment variable.
4. `curl -s -X POST http://localhost:8001/cases/DSP-031597/draft | python3 -m json.tool` — `response_state` should now be `DRAFT_READY`, `DRAFT_FLAGGED`, or `DRAFT_BLOCKED` (a real generation happened) instead of `GENERATION_UNAVAILABLE`.

**No key was configured when this document was written**, so every live check below used `FakeLLMProvider` or exercised the `GENERATION_UNAVAILABLE` path. `OpenRouterLLMProvider`'s HTTP request/response handling is fully exercised in `tests/test_llm_provider.py` against `httpx.MockTransport` (a fake in-process transport — real request-building and response-parsing code paths, zero network calls).

A key was configured later, and the live path (including real failure modes returned by the provider) is exercised end-to-end — see [docs/phase8-llm-provider.md](phase8-llm-provider.md) for the current, live-verified status and the exact model-availability evidence.

### Model selection (verified, not guessed)

The spec explicitly warns against blindly using OpenRouter's `openrouter/free` auto-router, since it can silently route across different underlying models between requests — undermining a reproducible demo. Instead, the model was chosen by querying OpenRouter's own public, unauthenticated `GET /api/v1/models` endpoint and its per-model `/endpoints` sub-resource (no key needed for either — this is public catalog data), filtering for free models that report `tools` in `supported_parameters` and confirming `supports_tool_choice.function: true` at the *actual serving endpoint* level (the top-level model listing can show broader parameter support than any single serving endpoint actually honors — checking both mattered):

```bash
curl -s "https://openrouter.ai/api/v1/models/nvidia/nemotron-3-super-120b-a12b:free/endpoints" | python3 -m json.tool
```

Selected: **`nvidia/nemotron-3-super-120b-a12b:free`**

| Property | Verified value |
|---|---|
| Pricing | `prompt: "0"`, `completion: "0"` (genuinely $0, not just discounted) |
| Served by | NVIDIA directly (single provider — not aggregated across many third-party quantizations with varying capability) |
| `supports_tool_choice` | `{"function": true, "required": true}` — forced/named tool-choice works, not just `"auto"` |
| `supported_parameters` | includes `tools`, `tool_choice`, `response_format`, `structured_outputs`, `seed` |
| Context length | 262,144 tokens |

Two other free candidates (`z-ai/glm-5.2:free`, `google/gemma-4-31b-it:free`) also verified to support forced tool-choice and would be reasonable alternatives; `minimax/minimax-m3:free` was checked and rejected (`supports_tool_choice.function: false`). Changing `LLM_MODEL` to a different free model is supported, but `OpenRouterLLMProvider.__init__` will refuse to start if the configured string doesn't end in `:free` (see the free-tier safety note below) — verify any replacement model's `supports_tool_choice.function` the same way before switching.

### Free-tier safety

- `OpenRouterLLMProvider.__init__` raises `ValueError` (caught by `get_llm_provider()` and turned into a clean `GENERATION_UNAVAILABLE`, never a crash) if `LLM_MODEL` does not end in `:free` — a misconfigured paid model string fails closed rather than being silently called.
- The request body always names exactly one `model` string. OpenRouter's multi-model fallback/routing parameters are never sent, so a request can never silently land on a different (possibly paid) model.
- **No retry logic anywhere.** A failed request (network error, timeout, non-200, malformed output) raises `LLMGenerationError` once; nothing in `OpenRouterLLMProvider` or `generation.py` retries. An automatic retry loop is exactly what could silently exhaust a free model's daily request quota (OpenRouter documents a 50-request/day limit on unfunded free accounts), so there isn't one — verified by `test_openrouter_does_not_retry_on_failure`.
- The API key is never logged or included in an exception message — error text is built from the HTTP response body only, truncated to 500 characters; the request object (which carries the `Authorization` header) is never stringified into a log or error. Verified by `test_openrouter_error_message_never_contains_the_api_key`.

## Part K — Evaluation

`scripts/evaluate_evidence_intel.py` — 8 hand-constructed, deterministic cases (NOT the locked test set, not train/validation — a controlled synthetic benchmark, per the spec's own allowance for this when exact real-world grounding labels don't exist). Each case has a *known* expected outcome for gap detection and for whether the overall response should block. Latest run:

| Metric | Result |
|---|---|
| Evidence-gap critical-detection accuracy | **100%** (8/8) |
| Retrieval reason-code relevance | **100%** (0 cross-reason-code leaks across 48 retrieved chunks) |
| Retrieval required-guidance hit rate | **100%** (every case with a critical gap retrieved a chunk addressing it) |
| Grounding: supported rate | 56% |
| Grounding: unsupported rate | 22% |
| Grounding: invalid-reference rate | 11% |
| Grounding: partially-supported rate | 11% |
| Blocked-response rate | 38% (3/8 cases) |
| Blocked-prediction accuracy (vs. expected) | **100%** (8/8) |

The 8 cases: complete strong evidence, missing critical evidence, contradictory evidence, weak evidence, unsupported-claim opportunity, unknown/missing evidence field, a reason-code-mismatch guard (proves retrieval never leaks across reason codes), and multiple evidence sources supporting one claim (positive control). Full per-case detail in `artifacts/evaluation/evidence_intel_evaluation.json`.

**Honesty note on the grounding rates**: the 56%/22%/11%/11% split is a property of the 8 *test fixtures* (which were deliberately constructed to include several bad-claim scenarios, per Part L's requirement), not a measurement of how often a real LLM hallucinates. It should be read as "the verifier correctly classified 8/8 constructed scenarios," not as "44% of real generated claims are bad."

## Part L — Adversarial Tests (mandatory, headline safety demonstration)

`tests/test_adversarial_grounding.py` — one test per required scenario, all deterministic (a `FakeLLMProvider` stands in for a model that *might* hallucinate this way, so the demonstration is 100% reproducible rather than depending on whether a real model happens to hallucinate today):

| Adversarial scenario | Test | Result |
|---|---|---|
| Fabricated delivery date | `test_adversarial_fabricated_delivery_date` | UNSUPPORTED |
| Missing proof-of-delivery cited as present | `test_adversarial_claims_missing_evidence_is_present` | UNSUPPORTED |
| Contradictory timestamps | `test_adversarial_contradictory_timestamp` | UNSUPPORTED |
| Evidence from another case | `test_adversarial_cross_case_evidence_contamination` | INVALID_REFERENCE |
| Nonexistent evidence ID | `test_adversarial_nonexistent_evidence_id` | INVALID_REFERENCE |
| Guaranteed dispute win | `test_adversarial_outcome_guarantee` (+ 4 phrasing variants) | UNSUPPORTED |
| Fabricated policy requirement | `test_adversarial_fabricated_policy_source` | INVALID_REFERENCE |
| Multiple sources for one claim (positive control) | `test_multiple_valid_evidence_sources_for_one_claim_is_supported` | SUPPORTED |

Plus an end-to-end reproduction of the exact Part S demo scenario (`test_end_to_end_mixed_draft_is_blocked_by_a_single_bad_claim`): two supported claims and one unsupported claim in the same draft still produce overall `DRAFT_BLOCKED` — a single bad claim is never averaged away by good ones.

## Part M — Versioning

| Component | Version |
|---|---|
| Evidence-gap / evidence-packet schema | `evidence-v1` |
| Knowledge base | `knowledge-v1` |
| Retrieval configuration | `retrieval-v1` |
| Prompt | `prompt-v1` |
| Response schema | `response-v1` |
| Verifier configuration | `verifier-v1` |

All defined in one place (`app/evidence_intel/versions.py`), mirroring `app/ml/schema.py`'s `MODEL_VERSION` and `app/decision/schema.py`'s `DECISION_POLICY_VERSION` pattern. Every `/draft` and `/verify` response carries all relevant version strings, so any output is traceable to the exact code+data that produced it.

## Locked-data protection (Part O)

Verified before and after implementation:

```
locked test checksum: e1e8cd5054c92fd399c50fa733c0256ec05bea6c13c80a15165c7cd5d0693b5c   (UNCHANGED)
git diff --stat -- data/locked/test/                                                    (empty)
```

Nothing in Phase 4 reads `data/locked/test/`, `data/generated/`, or any outcome/target field — the evidence gap analyzer and packet builder only ever see a case's `reason_code` and its own evidence rows (never `favorable_outcome`, `recovery_amount`, or any other Phase 1 label), and the 8-case evaluation benchmark is entirely synthetic, built in-process, never touching the dataset at all.

## Hardening pass (verifier-v1.1 / prompt-v1.1)

The first live OpenRouter run (`DSP-031597`, real model response, not `FakeLLMProvider`) surfaced two real defects the pre-existing test suite hadn't caught, plus a second-order issue found while fixing the first. All three were root-caused and fixed, not patched around:

1. **A claim cited a missing evidence_id while correctly describing it as absent.** Root cause: `prompt.py`'s "Available Evidence IDs" list actually included *unavailable* evidence_ids — the model had genuinely been told it could cite them. Fixed by splitting the prompt into a "citable" list (available only) and a separate "MISSING — no ID exists to cite" list, plus an explicit prompt rule (`prompt-v1.1` rule 2) that citing a missing item's ID is never allowed, for either direction of claim.
2. **The generated `response_body` ended mid-sentence** (`"Proof of delivery is: "`). Nothing checked for this. Fixed with a new deterministic check, `verifier.is_text_complete()` (must end in `.`/`!`/`?`, optionally wrapped in a closing quote/paren) — applied to every claim's `text` and, via the new `verify_response_body()`, to the overall `response_body`. A new `CLAIM_INCOMPLETE` status was added (additive to the existing four; `safety.py` treats it as blocking, same as `UNSUPPORTED`/`INVALID_REFERENCE`).
3. **A claim rhetorically waved away the missing evidence**: "Despite the absence of proof of delivery, [other evidence] supports that the goods were delivered." No citation-based check catches this (it cited zero missing evidence_ids — the overreach was purely in the prose). Fixed with a narrow, deterministic text-pattern guard (`_is_inference_overreach`): triggers only for `claim_type="inference"` claims that (a) name an actually-missing required evidence type, (b) use an absence-cue ("despite", "even without", ...), and (c) still conclude a support word ("supports", "confirms", ...). Explicitly not NLI/semantic understanding — three independent structured/textual signals, per the hardening request's constraint.
4. **Second-order finding while re-testing live**: the model correctly adopted the new "state absence with empty `evidence_ids`" pattern from fix 1 — but the pre-existing "a claim citing nothing is UNSUPPORTED" rule then rejected that *correct* behavior, since there is no ID to cite for something that doesn't exist. Fixed with a narrow carve-out (`_is_pure_missing_evidence_statement`): a zero-citation claim is `SUPPORTED` if it names a genuinely-missing evidence type and draws no support/proof conclusion from it; otherwise the original "cites nothing" rejection still applies unchanged.

All four fixes are covered by `tests/test_hardening_pass.py` (25 tests), including exact reproductions of the live C15/C16/dangling-response_body claims and guards proving the new carve-outs don't over-trigger on ordinary claims. Re-run against the real model afterward: `response_state` went from `DRAFT_BLOCKED` (1 unsupported claim, dangling response_body) to `DRAFT_READY` (10/10 verifications `SUPPORTED`) on the same case.

**One residual, out-of-scope finding, reported honestly rather than hidden**: in the post-fix live `DRAFT_READY` response, the final sentence of `response_body` read "...but proof of delivery and refund request evidence." — grammatically missing a predicate (should end "...are missing"), yet it still ends with a period, so `is_text_complete()` correctly reports it as punctuation-complete. Distinguishing "ends with a period" from "is a grammatically complete sentence" requires actual grammatical/semantic parsing — explicitly out of scope per this hardening request's "do NOT try to implement general NLI/semantic verification" constraint, and no safe punctuation-only heuristic exists for it (any pattern strict enough to catch a dropped predicate would also reject ordinary, legitimately complete sentences ending in a noun phrase). This is left as a known gap for human review to catch, which is exactly why `response_state` is decision support, not an auto-send.

## Limitations (stated plainly)

1. **`OpenRouterLLMProvider` has now been exercised against a real network response** (the hardening-pass live run above) — this superseded an earlier draft of this document that said otherwise. `AnthropicLLMProvider` remains unexercised against a real response in this environment (not used for the demo; no Anthropic key configured).
2. **The date-fabrication check is regex-based**, not a full date-understanding system. It catches literal date strings that don't appear in cited evidence values; a claim that describes a date in prose without a matching literal pattern (e.g., "delivered the following week") would not trigger it. This is a known gap, not a claimed complete solution.
3. **The outcome-guarantee and inference-overreach checks are keyword/phrase-based.** A sufficiently creative paraphrase of either could evade them. Both are real, tested safety nets (the overreach guard is proven against the exact live phrasing that motivated it), not a claim of perfect coverage.
4. **The weak-evidence threshold (`0.3`) is an illustrative default**, not derived from any calibration against real outcomes — same honesty posture as Phase 3's decision thresholds.
5. **The evaluation suite's grounding rates reflect 8 constructed fixtures, not empirical LLM hallucination rates** — see the honesty note in Part K.
6. **No semantic/NLI-based verification is implemented** — the spec allows this as an optional secondary signal; deterministic ID+content checks were chosen instead because they're exactly as reliable as the code that runs them, satisfying "prefer direct comparison against case fields" and "do not make an LLM the sole authority" without adding a second model dependency. The residual finding in the "Hardening pass" section above (a punctuation-complete but grammatically-incomplete sentence) is the concrete cost of that choice.
7. **The knowledge base is 51 chunks from 2 sources** (both documented with provenance in `data/reference/sources.json` — Stripe and Verifi/Visa public documentation). It is not a comprehensive dispute-guidance corpus; it's exactly as large as Phase 1's reference data, which this phase deliberately did not expand (no new scraping/sourcing work was in scope).
8. **`is_text_complete()` checks punctuation, not grammar.** See the residual finding above — a dropped predicate before a period is not caught. Human review remains mandatory for every draft regardless of `response_state`.

## What Phase 4 does NOT do

No automatic submission of anything, ever — not to a customer, not to a card network, not to Razorpay's own systems. No RAG/LLM was used anywhere in Phase 1–3 (unaffected). No embeddings, no vector database (TF-IDF over 51 chunks needs neither). No frontend changes (none required — the four new endpoints follow the exact response-shape conventions Part P asks for, ready for the existing Risk Command Center to consume whenever it adds these views). `POST /cases/{id}/decision` and `/score` are unchanged and still the source of truth for winnability/economics; Phase 4 only ever *reads* their output.
