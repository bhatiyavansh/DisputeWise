# Evaluation

This document is the single reference for how DisputeWise was evaluated, what the numbers mean, and what they don't. It intentionally does not repeat the full methodology narrative already in [phase2.md](phase2.md), [phase3.md](phase3.md), and [phase4.md](phase4.md) — see those for the detailed reasoning behind each choice; this is the results-and-protocol summary.

## Dataset split

50,000 synthetic chargeback cases, generated with a fixed seed (42), split at the **customer** level so no customer's disputes straddle two splits:

| Split | Cases | Purpose |
|---|---|---|
| Train | 35,115 | Model fitting |
| Validation | 7,439 | Threshold selection, calibration method selection, decision-policy exploration, portfolio/policy-playground defaults |
| Locked test | 7,446 | The **one** official evaluation number, read once |

## Locked test protocol

`data/locked/test/` is generated once and frozen; `data/metadata/locked_test_metadata.json` records its generation seed, row counts, and a SHA-256 checksum over the CSVs:

```
e1e8cd5054c92fd399c50fa733c0256ec05bea6c13c80a15165c7cd5d0693b5c
```

Every official evaluation script (`scripts/evaluate_locked_test.py`, `scripts/evaluate_locked_decisions.py`) re-verifies this checksum **before and after** it runs, and refuses to proceed if it has drifted. No script that reads the locked test set fits, calibrates, or tunes anything against it — that all happens on train/validation only, before the locked test set is ever touched.

Reproduce:

```bash
docker compose run --rm backend python /scripts/evaluate_locked_test.py
docker compose run --rm backend python /scripts/evaluate_locked_decisions.py
```

## Leakage prevention

- `app/ml/features.py`'s `build_features()` takes `disputes`, `transactions`, `customers`, `evidence` — no `outcomes` parameter exists, so the target (`favorable_outcome`) is structurally unreachable from feature construction, not just conventionally excluded.
- `recovery_amount` was audited and found to be a near-perfect proxy for the target (non-null iff `favorable_outcome` is true) and is excluded by the same mechanism.
- `app/ml/schema.py`'s `FORBIDDEN_COLUMNS` names every excluded field and why, so the exclusion is auditable rather than folklore.
- The customer-level split means no customer's historical behavior leaks across train/validation/test.
- `scripts/audit_model_data.py` fails loudly on split-integrity or leakage problems before any model is trained.

## ML metrics (locked test, n = 7,446)

| Metric | Value |
|---|---|
| ROC-AUC | 0.8990 |
| PR-AUC | 0.9334 |
| Precision | 0.8589 |
| Recall | 0.8705 |
| F1 | 0.8647 |
| Brier score | 0.1217 |
| ECE | 0.0122 |
| FPR | 0.2333 |
| FNR | 0.1295 |

Confusion matrix at the operating threshold (0.44, selected on validation by F1-max, never adjusted on test): TP 4,019 · TN 2,169 · FP 660 · FN 598.

Validation ROC-AUC is 0.8996 — within 0.001 of the locked-test figure, indicating no overfitting to validation either.

### Baseline comparison

Three evidence-completeness baselines (overall completeness, high-relevance completeness, high-relevance strength) were computed as sanity checks — "how well would a rule that just counts available evidence do?" The strongest of the three:

| | ROC-AUC | PR-AUC | F1 | Brier |
|---|---|---|---|---|
| Best baseline (evidence-strength rule) | 0.7579 | 0.7987 | 0.7715 | 0.2094 |
| DisputeWise model | **0.8990** | **0.9334** | **0.8647** | **0.1217** |

## Decision evaluation

Locked test (n = 7,446), under the production decision policy (`decision-v1`, `contest_cost=₹300`, `recovery_rate=1.0`):

| Bucket | Volume | Actual favorable-outcome rate |
|---|---|---|
| CONTEST | 27.22% (n=2,027) | 91.2% |
| HUMAN_REVIEW | 50.56% (n=3,765) | 66.2% |
| DO_NOT_CONTEST | 22.21% (n=1,654) | 16.6% |

Validation shows the same shape (26.3% / 90.7%, 50.8% / 66.2%, 22.9% / 16.9%) — the policy is not overfit to either split.

**Policy sensitivity, not hidden.** Under the ₹300 assumption, a naive contest-everything baseline realizes more total value on validation (≈₹10.35M) than the confidence-gated policy (≈₹5.40M), because filing costs so little relative to typical dispute value that even the lowest-confidence bucket is worth pursuing. At ₹5,000 the ranking flips hard: contest-everything falls to ≈−₹24.6M while the policy holds ≈+₹5.40M. This says more about the ₹300 assumption than about the model — the model separates the two extremes cleanly (91.2% vs 16.6% favorable) at any cost. The policy playground (`POST /policy/simulate`) makes this explorable directly against real portfolio data, and never against the locked test set.

Reproduce: `docker compose run --rm backend python /scripts/evaluate_decisions.py` (validation, against baselines) and `evaluate_locked_decisions.py` (official).

## Evidence intelligence evaluation

An 8-case **constructed** benchmark (`scripts/evaluate_evidence_intel.py`, `tests/test_adversarial_grounding.py`), deterministic — uses `FakeLLMProvider`, no API key or network call required:

| Metric | Result |
|---|---|
| Evidence-gap critical-detection accuracy | 100% (8/8) |
| Retrieval reason-code relevance | 100% |
| Required-guidance hit rate | 100% |
| Blocked-prediction accuracy | 100% (8/8) |
| Adversarial verifier scenarios | **13/13** |

**This is a constructed benchmark, not a real-world hallucination-rate estimate.** 100% here means the 8 specified scenarios (and the 13 adversarial grounding scenarios) all resolved exactly as designed — a fabricated evidence ID is rejected, a claim citing available evidence is accepted, one bad claim blocks an otherwise-good draft, and so on. It says the verifier's deterministic logic is correct on the cases it was designed to catch; it says nothing about the rate of hallucination in unconstrained real-world generation.

Reproduce: `docker compose run --rm backend python /scripts/evaluate_evidence_intel.py`.

## Limitations of this evaluation

- All metrics above are on a **synthetic** dataset generated by a known process, not real chargeback outcomes.
- The 8-case evidence benchmark and the 13 adversarial scenarios are hand-constructed to exercise specific failure modes — they establish correctness on those modes, not a general accuracy rate.
- `contest_cost` and `recovery_rate` are prototype assumptions; every decision-evaluation number above is conditional on them (see the sensitivity finding).
- Verifier checks (date consistency, guarantee-language detection) are regex/pattern-based, not a semantic entailment model — a claim can be textually well-formed but pass or fail on grounds a human reader might weigh differently.
- Free LLM provider reliability is out of DisputeWise's control; live generation is best-effort and can be unavailable — see [phase8-llm-provider.md](phase8-llm-provider.md).
