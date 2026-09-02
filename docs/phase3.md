# Phase 3 — Cost-Sensitive Decision Engine

Phase 2 answers *"how likely are we to win this dispute?"* Phase 3 answers *"is it economically worth contesting?"* It turns the calibrated probability into one of three recommendations — **CONTEST**, **HUMAN_REVIEW**, or **DO_NOT_CONTEST** — using a transparent expected-value model. It never submits, contests, or otherwise acts on a dispute. Every output is decision support for a human.

## Architecture

```
      case
       │
       ▼
Phase 2 calibrated P(win)        (unchanged; reused, not recomputed)
       │
       ▼
recoverable amount = dispute_amount × recovery_rate
       │
       ▼
expected_recovery = P(win) × recoverable_amount
expected_net_value = expected_recovery − contest_cost
       │
       ▼
decision policy      (app/decision/policy.py)
       │
  ┌────┼────┐
  ▼    ▼    ▼
CONTEST  HUMAN_REVIEW  DO_NOT_CONTEST
```

Code: `backend/app/decision/{config,engine,policy,schema,evaluation}.py`, `backend/app/services/decision_service.py`, `backend/app/api/decisions.py`. Phase 2's `app/ml/` package is untouched — `decision_service.py` calls `scoring_service.score_case()` for the probability, evidence summary, and SHAP factors, and adds exactly one more piece of data scoring doesn't need: the dispute's amount.

## Data classification: observed, model output, assumption

This distinction matters enough to state explicitly, since conflating them is how a prototype quietly becomes mistaken for verified economics.

| | Source | Example |
|---|---|---|
| **Observed data** | Phase 1 dataset | `dispute_amount`, evidence records, reason code |
| **Model output** | Phase 2 | `calibrated_probability` — a real number from a trained, calibrated LightGBM model, evaluated once, honestly, on the locked test set |
| **Prototype assumptions** | Phase 3, this document | `contest_cost`, `recovery_rate`, all four decision thresholds |

**The assumptions are not Razorpay facts.** They are configuration defaults chosen to be plausible and to make every formula in this document produce sane, explainable numbers — nothing more. In production they would need to be calibrated from real Razorpay/network economics (actual representment fees, actual partial-recovery rates net of processor and network fees, actual operational cost of preparing evidence). None of that data was available for this buildathon submission, so none of it is claimed.

## Core economic model

```python
recoverable_amount  = dispute_amount * recovery_rate
expected_recovery   = calibrated_probability * recoverable_amount
expected_net_value  = expected_recovery - contest_cost
break_even_probability = contest_cost / recoverable_amount   # undefined if recoverable_amount == 0
```

All four functions are pure and unit-tested in isolation (`app/decision/engine.py`, `tests/test_decision_engine.py`). Nothing here is hidden behind a single score — `POST /cases/{id}/decision` returns every intermediate number.

## Configuration (`app/decision/config.py`)

| Field | Default | Meaning |
|---|---|---|
| `contest_cost` | 300.0 | Flat estimated cost of preparing and submitting a contest (currency units matching `dispute_amount`) |
| `recovery_rate` | 1.0 | Fraction of `dispute_amount` actually recoverable if won |
| `min_expected_net_value` | 0.0 | Reference EV a CONTEST must clear |
| `review_margin` | 50.0 | Width of the "too close to call economically" band around `min_expected_net_value` |
| `high_confidence_probability` | 0.65 | Minimum P(win) required for CONTEST |
| `low_confidence_probability` | 0.35 | Maximum P(win) allowed for DO_NOT_CONTEST |
| `require_high_relevance_evidence_for_contest` | `True` | Evidence gate (see below) |

Validated with pydantic (`tests/test_decision_config.py`): `contest_cost >= 0`, `0 <= recovery_rate <= 1`, `review_margin >= 0`, both probability thresholds in `[0, 1]`, and `high_confidence_probability` must strictly exceed `low_confidence_probability`. Invalid configuration raises at construction time rather than producing a nonsensical policy silently.

Every field is overridable via an environment variable prefixed `DISPUTEWISE_` (e.g. `DISPUTEWISE_CONTEST_COST=450`), with these defaults used for local development and this submission's evaluation.

**Why `contest_cost` is a single flat number.** The spec allows for `operational_cost`, `network_fee`, `evidence_preparation_cost` as separate fields. We deliberately did not itemize: with zero verified data on what any of those actually cost on Razorpay's network, itemizing would just be inventing three numbers instead of one, with no more truth value and a false appearance of precision. One transparent, clearly-labeled assumption is more honest than three.

## Decision policy (`app/decision/policy.py`)

The primary signal is **expected net value**, not probability alone — a case is never recommended for CONTEST purely because the model is confident, and never purely because the raw economics look positive:

```python
clearly_positive = expected_net_value >= min_expected_net_value + review_margin
clearly_negative = expected_net_value <  min_expected_net_value - review_margin
confident_win     = calibrated_probability >= high_confidence_probability
confident_loss    = calibrated_probability <= low_confidence_probability

if clearly_positive and confident_win:      → CONTEST        (subject to the evidence gate below)
elif clearly_negative and confident_loss:   → DO_NOT_CONTEST
else:                                       → HUMAN_REVIEW
```

This is deliberately the simplest policy that uses both signals: two threshold checks, no learned weights, no scoring function beyond arithmetic. Every branch is auditable by reading `policy.py` directly. The `review_margin` band guarantees that a case whose economics are ambiguous is *never* a firm decision, regardless of model confidence — this directly implements the spec's "expected_net_value near zero → HUMAN_REVIEW" requirement, and also catches the case where good economics coexist with mediocre confidence (or vice versa): four scenarios, three of which route to HUMAN_REVIEW, by design.

We use the term `decision_confidence` nowhere in the code or API. "Confidence" in this document always means `calibrated_probability` against an explicit threshold — never a statistical confidence interval, which is not implemented and would be dishonest to imply.

### Evidence-aware routing (the one override)

If a CONTEST recommendation would fire but a high-relevance evidence type (per this case's reason code, using Phase 1's own `relevance` field) is missing entirely, the recommendation is downgraded to `HUMAN_REVIEW`:

> *"Economics and model confidence both favor contesting ..., but key evidence for this reason code is missing on file (proof_of_delivery). Routed to human review rather than recommending CONTEST on evidence that may not actually exist to submit."*

This is the **only** evidence-based rule in the policy, and it is one-directional: it can only turn CONTEST into HUMAN_REVIEW, never the reverse, and it never touches DO_NOT_CONTEST. It does not duplicate the LightGBM model — it reads `evidence_summary.missing_key_types`, the same field `/score` already returns, without any independent scoring. The rationale is narrow and stated in the code: a CONTEST recommendation asks a human to spend `contest_cost` on the strength of evidence that, per Phase 1's own taxonomy, doesn't exist for this dispute type — regardless of how confident the model is from other signals (customer history, amount, etc). It's toggleable via `require_high_relevance_evidence_for_contest`.

## Break-even probability and sensitivity analysis

```
break_even_probability = contest_cost / recoverable_amount
```

Example: recoverable amount ₹10,000, contest cost ₹300 → break-even at 3%. *"At current assumptions, this case becomes economically positive above a 3% win probability."* Undefined (returned as `null` with an explanation) when `recoverable_amount == 0`.

The sensitivity curve (`sensitivity_curve()`, exposed on every `/decision` response) reports `expected_net_value` at `calibrated_probability ± {0.10, 0.05, 0}` (clipped to `[0, 1]`, duplicates from clipping collapsed). **This is presentational only** — `test_sensitivity_curve_does_not_affect_decision` asserts it never feeds back into the decision itself.

## API

`POST /cases/{case_id}/decision` — implemented, replacing the Phase 1/2 501 stub (same pattern as `/score` in Phase 2: the one Phase 1/2 test asserting a 501 was intentionally inverted, not silently deleted). Every response carries `model_version`, `feature_schema_version`, and `decision_policy_version` (`decision-v1`), making the complete decision reproducible from three version strings. 404 for an unknown case; 422 if the underlying probability/amount are somehow invalid (`InvalidCaseInputError`); 503 if model artifacts aren't built, same as `/score`.

`/draft` remains a deliberate 501 stub — Phase 4 scope.

## Offline evaluation

`scripts/evaluate_decisions.py` (validation) and `scripts/evaluate_locked_decisions.py` (locked test, **run once, official**) share `app/decision/evaluation.py` so both compute buckets identically. The locked-test script mirrors `evaluate_locked_test.py`'s discipline exactly: verifies the checksum before and after, never retrains, never refits calibration, never tunes a threshold against the test set — `DecisionConfig`'s defaults are fixed in code before either script runs.

### Validation vs. locked test (consistency check)

| Bucket | Validation (n=7,439) | Locked test (n=7,446) |
|---|---|---|
| CONTEST | 26.3% (n=1,959), favorable 90.7% | 27.2% (n=2,027), favorable 91.2% |
| HUMAN_REVIEW | 50.8% (n=3,776), favorable 66.2% | 50.6% (n=3,765), favorable 66.2% |
| DO_NOT_CONTEST | 22.9% (n=1,704), favorable 16.9% | 22.2% (n=1,654), favorable 16.6% |

Bucket sizes and favorable-outcome rates agree closely between validation and the locked test — the policy is not overfit to validation, which is the main thing this comparison is checking for.

**Reading the bucket favorable rates.** CONTEST cases really do win far more often (≈91%) than HUMAN_REVIEW (≈66%) or DO_NOT_CONTEST (≈17%) cases — the policy is sorting cases in the right direction. DO_NOT_CONTEST at 16.6% (not 0%) is expected and correct: DO_NOT_CONTEST requires low *confidence*, not certainty of loss, so some of these cases still win — the policy is honest about operating on probability, not prophecy.

### Baseline comparison (validation split)

| Policy | CONTEST volume | E[net value], CONTEST bucket | Realized net value, CONTEST bucket |
|---|---|---|---|
| **DisputeWise decision-v1** | 1,959 (26.3%) | ₹5,376,927 | ₹5,400,055 |
| A: contest everything | 7,439 (100%) | ₹10,168,449 | ₹10,347,063 |
| B: P(win) ≥ 0.50 | 4,433 (59.6%) | ₹9,875,943 | ₹9,875,360 |
| C: evidence completeness ≥ 0.70 | 5,434 (73.1%) | ₹8,231,799 | ₹8,469,474 |

**This is not cherry-picked, and it is worth reading honestly rather than glossing over: under the default cost assumptions, "contest everything" captures more total realized net value than our policy.** Here's why, stated plainly: with `contest_cost=300` tiny relative to typical dispute amounts (median ≈₹1,176), the break-even probability for most cases is only a few percent — almost *any* non-trivial win probability clears the economic bar. That means, under these defaults, `expected_net_value` alone rarely disqualifies a case; the **confidence threshold** (`high_confidence_probability=0.65`) is the actual binding constraint on our policy's CONTEST volume, not the economics. HUMAN_REVIEW cases have a 66.2% actual favorable rate — well above the ~3% break-even for a typical amount — so a large amount of realizable value sits in that bucket precisely because our policy is deliberately conservative about model confidence, not because the economics say no.

This is a genuine, actionable finding, not a flaw to hide: it says the *current default* `high_confidence_probability=0.65` is calibrated for caution (avoid recommending CONTEST on cases we're not sure about) rather than for maximizing captured volume, and that a real deployment should treat this as a tunable dial, informed by real per-case operational cost (not the simplified flat `contest_cost` used here) and real institutional risk appetite — not something this prototype should decide unilaterally by quietly picking defaults that make the headline number look best. We did not retune the defaults after seeing this result; the config shipped is the one described above, chosen before evaluation, and the honest comparison is reported as-is.

Baseline C (evidence completeness) sits between B and "everything" — it captures more volume than our policy but with a lower CONTEST-bucket favorable rate (64.3% vs 90.7%), since it ignores the model probability entirely.

### Portfolio totals (validation, all three buckets, `E[net]` summed across CONTEST + HUMAN_REVIEW + DO_NOT_CONTEST using each case's own economics regardless of the bucket it landed in)

DisputeWise decision-v1 total across all buckets: **₹10,168,449** expected net value — nearly identical to Baseline A's CONTEST-only total, because almost every case in this dataset has positive expected value; our policy's role is *which* cases get a confident CONTEST recommendation now versus which get routed to a human first, not whether value exists at all.

## Fairness and evidence-aware routing carried over from Phase 2

No protected attributes are used anywhere in the decision engine — it consumes only `calibrated_probability` (already fairness-audited in Phase 2; see docs/phase2.md), `dispute_amount`, and the evidence-gap flag. Nothing new is added.

## Limitations

Stated as plainly as Phase 2's:

1. **Every cost/rate assumption is a prototype default, not verified Razorpay economics** — see the table at the top of this document. `contest_cost=300` and `recovery_rate=1.0` were chosen to be plausible and produce sane example numbers, not sourced from any real fee schedule.
2. **`contest_cost` is a single flat number.** Real operational cost varies by reason code, evidence volume, and merchant — none of that variation is modeled here.
3. **`recovery_rate=1.0` assumes full face-value recovery.** Real chargeback wins are frequently netted against network/processor fees; this prototype does not model that.
4. **The underlying probabilities are themselves built on synthetic training data** (see docs/phase2.md's limitations — this compounds, it doesn't cancel out).
5. **The "contest everything" comparison above is not an endorsement of contesting everything.** It's an artifact of a tiny assumed `contest_cost` relative to typical amounts; with a more realistic (and currently unverified) operational cost, the ranking would very plausibly reverse. We report the number as measured, not adjusted to look favorable.
6. **`decision_confidence` as a statistical concept is not implemented.** Every mention of "confidence" in this document and the code is `calibrated_probability` against a threshold — not a confidence interval, not an uncertainty estimate.
7. **Thresholds (0.65 / 0.35 / ₹50 margin) are illustrative defaults**, not derived from any loss function or optimization — the spec explicitly asked for a simple, auditable policy over a mathematically optimal one, and that's what's implemented.

## Phase 3 boundary

Implemented: cost-sensitive decision engine, three-way policy, break-even/sensitivity analysis, evidence-aware routing, real `POST /cases/{id}/decision`, validation + locked-test decision evaluation, baseline comparison.

**Not** implemented (Phase 4+): RAG, embeddings, vector database, LLM response drafting, automatic evidence drafting, automatic submission, customer notifications, Razorpay production API integration, frontend. `POST /cases/{id}/draft` remains a deliberate 501 stub.
