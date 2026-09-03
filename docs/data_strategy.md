# Data Strategy

DisputeWise uses three distinct categories of data, each with a different purpose. They are stored in separate, clearly-named directories and must never be mixed:

| Directory | Category | Purpose |
|---|---|---|
| `data/generated/`, `data/locked/test/` | **Synthetic ML dataset** | Model training, validation, and locked held-out evaluation |
| `data/reference/` | **Public domain reference data** | Domain knowledge grounding the generator's assumptions; the RAG knowledge base (`knowledge-v1`) is built from this directory |
| `data/external/` | **External real-world benchmark (if any)** | Out-of-distribution sanity check against an already-trained model — never training data |

This document explains why, and how the pieces relate. It does not change or regenerate any existing dataset — see [docs/phase1.md](phase1.md) for the synthetic generator's own methodology, which is unchanged by this upgrade.

## 1. Why synthetic data is necessary

We need 50,000 labeled cases with a specific target (`favorable_outcome`) to train and evaluate a classifier, on a timeline (hackathon deadline) that makes waiting for real, labeled, case-level chargeback-outcome data impossible. As documented in [docs/external_data.md](external_data.md), that kind of data is commercially sensitive and not available publicly at any scale we could use. Synthetic generation is the only way to get a large, fully-labeled, reproducible dataset with a target we control and understand.

Synthetic generation also gives us properties real data usually can't offer within a hackathon timeline: an exactly-reproducible locked test set (see docs/phase1.md's "Reproducibility" section), full control over class balance across archetypes, and complete freedom from privacy/compliance concerns since no real cardholder or merchant data is involved anywhere in the pipeline.

## 2. Why real data is valuable (even though we don't have case-level labels)

Even without case-level outcome labels, real-world data is valuable for **grounding the shape of the input distributions** — transaction amounts, reason-code mix, authentication pass rates, evidence-availability rates, customer transaction frequency. Aggregate statistics of this kind are publicly documented by payment processors and networks (see `data/reference/`), even though case-level *outcomes* are not.

Public domain-knowledge sources are also valuable independent of the ML pipeline: they tell us which evidence types actually matter for which reason codes in real dispute processes (Visa/Mastercard/Amex compelling-evidence guidance), which is exactly the `relevance` structure our evidence taxonomy already encodes (see `data/reference/evidence_requirements.csv`) and will directly support Phase 4's RAG retrieval later.

## 3. Why real data cannot simply replace the synthetic dataset

Three hard blockers, in order of severity:

1. **No case-level outcome labels are legally available.** As detailed in `docs/external_data.md`, the one dataset we found with the right target semantics (validated/rejected chargeback outcomes) is under a confidentiality agreement and cannot be obtained or redistributed. Datasets that *are* public (Kaggle fraud-detection sets) label a different target entirely (transaction-level fraud, or chargeback occurrence) — using them would silently redefine `favorable_outcome` into something else.
2. **No locked, versioned, reproducible benchmark.** A defining property of our evaluation methodology is a byte-identical, checksummed held-out test set (`data/locked/test/`) that never changes across development iterations. Real-world data sourced from third parties comes with no such guarantee of stability, licensing continuity, or reproducibility.
3. **No control over confounds.** The synthetic generator lets us guarantee, by construction, that evidence, customer history, and reason code are the only things driving the label (via the latent logistic model in `scripts/generate_dataset.py`) — with realistic overlap and noise, but no hidden real-world confound (e.g. a merchant category, a specific bank's policies, a regional regulation) leaking into the label in ways we can't see or account for.

Real data therefore **calibrates** the synthetic generator's assumptions; it does not replace the generator's output as the primary training/evaluation set.

## 4. How real data can calibrate distributions

```
REAL-WORLD DATA (public aggregate statistics, domain documentation)
        │
        ▼
distributional statistics
  (amount skew, reason-code mix, auth pass-rates,
   evidence-availability rates, dispute frequency, ...)
        │
        ▼
synthetic generator parameters
  (scripts/generate_dataset.py: archetype tier probabilities,
   logit weights, missingness rates)
        │
        ▼
50k controlled, reproducible, fully-labeled cases
```

Concretely, statistics worth sourcing and feeding into future generator calibration include:

- **Transaction amount distribution** — real INR (or regional) transaction-amount skew, to sanity-check `base_amount = rng.lognormal(...)` in `generate_cases()`.
- **Dispute reason-code distribution** — the real mix of unauthorized/not-received/duplicate claims (payment-network aggregate stats), to sanity-check `reason_probs`.
- **Customer activity / transaction frequency** — how often real customers repeat-transact, to sanity-check the `n_customers = n_cases / 1.4` reuse assumption.
- **Missing-evidence rates** — how often 3DS/AVS/CVV/tracking data is actually captured in production systems, to sanity-check the `avail = {...}` missingness probabilities.
- **Temporal patterns** — real dispute-filing lag (transaction → dispute) and response-deadline conventions, to sanity-check the `dispute_created_at` / `response_deadline` sampling windows.
- **Chargeback frequency** — real dispute-rate-per-transaction-volume, relevant context for Phase 3's cost model later, not Phase 1/2 scope.

**This upgrade documents the architecture for this calibration step. It does not perform it.** `scripts/generate_dataset.py` is unmodified, `--seed 42 --n-cases 50000` still produces the exact dataset already locked, and no distributional parameter has changed.

## 5. How external data could eventually be used as a domain-shift benchmark

See `docs/external_data.md` §"How a future external benchmark could be performed" for the full procedure. In short: an external dataset with compatible target semantics, if one is ever obtained under a clear license, would be stored under `data/external/` labeled `EXTERNAL_BENCHMARK_ONLY`, and used to evaluate an already-trained model read-only — reported as a separate domain-shift metric, never blended into the primary synthetic-test metrics, and never used for training.

## 6. Why the locked synthetic test set remains the official internal evaluation set

The locked test set (`data/locked/test/`, checksummed in `data/metadata/locked_test_metadata.json`) is the only evaluation set that satisfies all of our requirements simultaneously: it's case-level, fully labeled with the exact target we need, reproducible byte-for-byte, versioned, free of licensing risk, and large enough (7,446 cases) for statistically meaningful precision/recall/F1/ROC-AUC/FPR reporting. No real-world dataset currently available to us satisfies more than one of those properties at once. Real and external data inform and calibrate the system around this benchmark; they do not replace it as Phase 2's official evaluation target.
