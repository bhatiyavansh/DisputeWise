# Phase 6 — New Dispute Simulation

`POST /simulate` runs a **hypothetical** dispute through the existing Phase 2/3/4 pipeline. It is scenario analysis: nothing is stored, and no production case endpoint is involved.

```
request → simulation case → [features-v1] → [risk-v1 + calibration]
       → [decision-v1] → [evidence-v1 gap] → [knowledge-v1 retrieval]
       → optional [prompt-v1.1 generation] → [verifier-v1.1]
```

## Reuse, not reimplementation

The service (`app/services/simulation_service.py`) calls into the modules that already own each step. It contains no feature engineering, no probability math, no decision thresholds and no verification rules of its own:

| Stage | Owned by | Simulation calls |
|---|---|---|
| Features + scoring | `app/ml/features.py`, `app/ml/model.py` | `scoring_service.score_parts()` |
| Decision | `app/decision/policy.py` | `evaluate_case()` |
| Evidence gap | `app/evidence_intel/gap_analyzer.py` | `analyze_gap()` |
| Packet | `app/evidence_intel/packet.py` | `build_packet()` |
| Retrieval | `app/evidence_intel/retrieval.py` | `retrieve_for_case()` |
| Generation | `app/evidence_intel/generation.py` | `generate_draft()` |
| Verification | `app/evidence_intel/verifier.py` | `verify_claims()`, `verify_response_body()` |

The one Phase 2 change was extracting `score_parts()` out of `score_case()` in `scoring_service.py` — the identical code path, now callable with in-memory case parts instead of ORM rows. `score_case()` is `score_parts()` plus the DB load. All pre-existing tests pass unchanged.

## No target leakage

- `SimulationRequest` is `extra="forbid"`, so any undeclared field is a 422 rather than being ignored.
- A `mode="before"` validator additionally refuses every name in `app/ml/schema.py`'s `FORBIDDEN_COLUMNS` **by name**, so a caller gets an explicit refusal rather than a generic one.
- No field in the model describes an outcome. `build_features()` still never receives the outcomes table.
- `tests/test_simulation.py` parametrizes over every `FORBIDDEN_COLUMNS` entry and asserts a 422 for each.

## No persistence

`simulation_service` takes no `Session` and imports no ORM model — the guarantee is structural, not a convention (asserted in `test_simulation_service_takes_no_db_session`). The response carries `is_simulation: true` and `trace.persisted: false`, and `test_simulation_persists_nothing` compares table counts before and after.

## Two documented modelling choices

Everything in the request is a fact a merchant knows before resolution. Two values the pipeline needs cannot be read straight off such a form, so `app/simulation/case_builder.py` derives them explicitly:

1. **Evidence `strength`.** In the Phase 1 dataset this is a random draw — `uniform(0.6, 1.0)` when the evidence corroborates the merchant, `uniform(0.0, 0.5)` when it is on file but unhelpful. A simulation cannot draw randomly and stay reproducible, so it uses the **midpoints** of those documented ranges (`0.8` / `0.25`) — the expected values of the distribution the model was trained on. Not a new business rule, and not tuned.
2. **Timestamps.** Features only ever use *differences* between timestamps, so simulation anchors them to a fixed instant (`SIMULATION_ANCHOR`). Identical requests therefore produce identical features. Wall-clock time appears only in `generated_at` metadata.

Evidence **relevance** is *not* one of these: it is read per reason code from `data/reference/`, the same authoritative source the gap analyzer uses (`test_evidence_relevance_comes_from_reference_data_not_the_request` proves it varies by reason code).

## Evidence availability

Each of the 16 evidence types is derived from the facts supplied:

- **Authentication / customer history** — the record exists either way (an AVS mismatch is still an AVS record).
- **Fulfillment** — the fact *is* the record: no delivery confirmation means no delivery-confirmation evidence to file. This is the gap the product exists to surface.
- **Cancellation / refund request** — on file either way, because "no request was made" is the state that *corroborates* the merchant.

Any of these can be overridden per request via `evidence_on_file` / `evidence_not_on_file`.

## The three demo scenarios

Verified live against the real model and policy; nothing was tuned to produce them:

| Scenario | P(win) | Decision | Why |
|---|---|---|---|
| Strong evidence, ₹25k | 0.9801 | **CONTEST** | coverage 1.0, expected net value +₹24,202 |
| Same case, `proof_of_delivery: false` | 0.9778 | **HUMAN_REVIEW** | CRITICAL gap → `evidence_gap_downgrade` |
| Weak, ₹800, no auth, 3 prior disputes | 0.0744 | **DO_NOT_CONTEST** | expected net value −₹240 |

The middle row is the product's core claim in one API call: **high winnability alone does not mean contest.**

## Frontend

`/simulation` (the SPA route — `/simulate` is a proxied API prefix, the same collision `/case/:id` works around). Reached via **“+ Simulate New Dispute”** in the sidebar.

Progressive-disclosure sections (Transaction / Authentication / Customer / Fulfillment / Communication / Response generation), a **Run simulation** button, and a pipeline strip: `SCORING → DECISION → EVIDENCE → KNOWLEDGE → RESPONSE → VERIFICATION`.

The strip does **not** fake progress timing. `/simulate` is one request, so the frontend genuinely cannot observe the backend moving between stages: while in flight every stage reads "running", and once the response lands each stage is marked from real evidence in the payload. A stage that did not run (generation is opt-in) is shown as `(not run)`, never as complete — and its version reports "not run" rather than a plausible-looking string.

Results are labelled **Scenario** throughout, and the provenance panel shows `persisted: no — scenario only`.

## Tests

`tests/test_simulation.py` — 45 tests: valid simulation, every stage actually invoked, invalid/missing input, unknown evidence types, contradictory overrides, target-field rejection (parametrized over all `FORBIDDEN_COLUMNS`), no persistence, determinism, version metadata for stages that ran, generation-unavailable handling, the verifier still blocking an invented evidence reference, and the three scenarios above.

`src/pages/SimulationPage.test.tsx` — 6 tests: scenario labelling, no API call until run, POST shape carries no target field, backend decision rendered verbatim (including a deliberately "inconsistent" high-probability HUMAN_REVIEW), not-run stages, and 422 surfaced as a validation error rather than a generic failure.
