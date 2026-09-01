# External Real-World Datasets — Investigation Notes

This document records what we looked for, what we found, and why nothing was merged into DisputeWise's training pipeline. It is investigation-and-decision documentation, not a data source itself.

## Why real-world data is desirable

The synthetic generator (`scripts/generate_dataset.py`) encodes our own assumptions about how authentication strength, fulfillment evidence, customer history, and reason code relate to dispute outcomes. Those assumptions are *plausible* (see [docs/data_strategy.md](data_strategy.md) for the model), but they are still assumptions. Real-world distributions — how often 3DS is actually present on disputed transactions, what fraction of goods-not-received cases actually have tracking data, how skewed real transaction amounts are — would let us check and recalibrate those assumptions instead of guessing.

## Why public chargeback outcome datasets are difficult to use directly

We searched for a public, case-level dataset of chargeback **dispute outcomes** (i.e., did the merchant win when contesting a chargeback — the same semantics as our `favorable_outcome` target). We did not find one that is both public and usable. Specifically:

- **Chargeback outcome data is commercially sensitive.** Payment processors, acquiring banks, and chargeback-management vendors (Chargeflow, Chargebacks911, Chargeback Gurus, Kount, etc.) all publish aggregate statistics and guidance, but their underlying case-level data is proprietary — it's their competitive product.
- **The one academic dataset we found with the right target semantics is not publicly redistributable.** A 2026 industry case study (Australasian Information Security Conference, DOI `10.1145/3793638.3793649`) analyzed 126,184 anonymized merchant transactions with chargeback claims, each labeled *validated* or *rejected* — genuinely the right target. It was provided to the researchers under a confidentiality agreement with the industry partner (Novatti Group Ltd.), and the paper states public release is not permitted. We reference it here as evidence that this *kind* of data exists and is being studied, not as a data source — we have no legal path to obtain or redistribute it.
- **The commonly-cited Kaggle "fraud" datasets solve a different problem.** We checked the two most prominent ones:
  - `mlg-ulb/creditcardfraud` ("Credit Card Fraud Detection") labels individual **transactions** as fraudulent or not (PCA-anonymized features, no reason code, no merchant response, no dispute process at all). This is *transaction-level fraud detection*, not *dispute-outcome prediction* — there is no "did the merchant contest and win" concept in this data at all.
  - `dmirandaalves/predict-chargeback-frauds-payment` ("Predict Chargeback Frauds") labels whether a transaction *became* a chargeback, not whether a merchant's *contest of* that chargeback succeeded. Same mismatch: it's upstream of our problem, not the same target.

  Per the explicit instructions for this upgrade, neither was added — merging either in, or reinterpreting their labels to look like `favorable_outcome`, would silently redefine our target and invalidate the whole modeling exercise.

## What target/features a compatible external dataset would need

For a dataset to be usable as an external benchmark (not training data) for DisputeWise, it would need, at minimum:

- **Target**: a case-level outcome of a *merchant's contest of a filed chargeback/dispute* (won/lost, or equivalent), not "was this transaction fraudulent" or "did a chargeback occur."
- **Reason code** (or something mappable to `unauthorized_transaction` / `goods_not_received` / `duplicate_charge`), since evidence relevance is reason-code-dependent in our model.
- **Evidence features**, or at least proxies for them: authentication signals (3DS/AVS/CVV), fulfillment signals (delivery/tracking), and/or customer history — enough to compute something comparable to our evidence matrix.
- **Legally clear reuse rights**: a license that permits us to store and evaluate against the data (public domain, CC-BY, or explicit research/redistribution permission).

## Datasets identified and their suitability

| Dataset | Target semantics | Suitable? | Why |
|---|---|---|---|
| Novatti Group chargeback validation study (ACSC 2026) | Chargeback validated/rejected (case-level) | **No** | Right semantics, but confidentiality-agreement data — not legally obtainable/redistributable |
| Kaggle `mlg-ulb/creditcardfraud` | Transaction fraud (binary) | **No** | Wrong target (fraud detection, not dispute-contest outcome); no reason code, no evidence features, no dispute process |
| Kaggle `dmirandaalves/predict-chargeback-frauds-payment` | "Became a chargeback" (binary) | **No** | Wrong target (chargeback occurrence, not contest outcome) |
| Payment-network/processor aggregate statistics (Visa, Mastercard, Stripe, Chargebacks911, etc.) | Aggregate win-rate / reason-code-mix statistics, not case-level | **Not case-level** | Useful for *distributional calibration* (see docs/data_strategy.md) — not usable as a benchmark dataset, since there's no per-case record to evaluate against |

## Decision

**No external dataset has been added under `data/external/`.** Per the guidance for this upgrade, forcing in a dataset with incompatible target semantics — or relabeling one to superficially match — would corrupt the benchmark rather than strengthen it. `data/external/` currently contains only a `README.md` explaining this state; nothing in it is loaded by any script, and it has no bearing on the synthetic dataset, the locked test set, or current model development.

If a suitable dataset becomes available later (e.g., a research release under a compatible license, or a data-sharing agreement), it should be added under `data/external/`, explicitly labeled `EXTERNAL_BENCHMARK_ONLY` in its own manifest entry, and used strictly as an out-of-distribution benchmark run against an already-trained model — never merged into `data/generated/` or `data/locked/test/`, and never used to retrain against.

## How a future external benchmark could be performed

Once/if a suitable dataset is identified:

1. Store it under `data/external/<dataset_name>/` with its own `manifest.json` (source, license, retrieval date, `status: "EXTERNAL_BENCHMARK_ONLY"`), following the same provenance pattern as `data/reference/sources.json`.
2. Map its reason codes / features to our schema *without* touching `scripts/generate_dataset.py` or any synthetic table.
3. Run the already-trained Phase 2+ model against it read-only, reporting the same metrics used on the locked synthetic test set (precision/recall/F1/ROC-AUC/FPR) *separately*, labeled as an out-of-distribution/domain-shift check — not blended into the primary evaluation numbers.
4. Treat a large gap between synthetic-test performance and external-benchmark performance as a signal to *recalibrate the generator's distributions* (see docs/data_strategy.md), not to retrain directly on the external data.
