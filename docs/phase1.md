# Phase 1 — Technical Notes

## Schema

Five tables, all FK-linked in a straight line: `customers → transactions → disputes → {evidence, outcomes}`. `disputes` is the "case" table — `dispute_id` (e.g. `DSP-000001`) is the case identifier used throughout the API.

Design choices worth calling out:

- **1:1 transaction:dispute.** Each case has exactly one underlying transaction. This is a deliberate simplification for Phase 1/2 (evidence-matrix building and a first classifier don't need multi-transaction cases); it can be relaxed later without touching the `customers`/`evidence`/`outcomes` tables.
- **Evidence is normalized, not a JSON blob.** Each evidence item is its own row (`evidence_type`, `available`, `value` (JSONB), `relevance`, `strength`). This lets Phase 2 build an evidence matrix (`case_id × evidence_type → strength`) with a straightforward pivot, and lets `relevance` vary per (`reason_code`, `evidence_type`) pair without any schema change.
- **`disputes.status` is a workflow status** (`open`, `evidence_submitted`, `under_review`, `closed`), sampled independently of `favorable_outcome`. It is *not* derived from the outcome — this avoids a trivial leakage path where the API's own status field gives away the label.
- **`disputes.scenario_archetype` and `disputes.split`** are generation provenance, not modeling features. Phase 2 should exclude `scenario_archetype` from the feature set (it's a generator-time label, unknowable for a real incoming case) — it's kept in the schema purely for dataset auditing and the archetype-level metrics in this doc.

## Evidence taxonomy

16 evidence types across four categories:

| Category | Types |
|---|---|
| Authentication | `three_ds`, `avs`, `cvv`, `device_match`, `ip_match` |
| Fulfillment | `delivery_confirmed`, `tracking_available`, `delivery_address_match`, `delivery_timestamp`, `proof_of_delivery` |
| Customer | `prior_order_history`, `prior_successful_orders`, `prior_disputes` |
| Communication | `customer_communication_available`, `cancellation_request`, `refund_request` |

`relevance` (`high`/`medium`/`low`) is assigned per (`reason_code`, `evidence_type`) — see `RELEVANCE_MAP` in `scripts/generate_dataset.py`. Example: authentication evidence is `high` relevance for `unauthorized_transaction` but `low` for `goods_not_received`; fulfillment evidence is the inverse.

## Data generation methodology

`scripts/generate_dataset.py` is fully vectorized with `numpy`/`pandas`, driven by a single `numpy.random.Generator(seed)`.

### Customers

~1 customer per 1.4 cases (`n_customers = n_cases / 1.4`). Each customer has a latent `quality ~ Beta(2.2, 2.2)` score (never written to the dataset — only its noisy downstream effects are), which drives:

- `account_age_days` (gamma-distributed, scaled by quality)
- `previous_order_count` (Poisson, rate ∝ quality)
- `previous_successful_order_count` (order count × a quality-driven success rate, `0.12 + 0.78·quality + noise`)
- `previous_dispute_count`, `previous_refund_count` (Poisson, rate ∝ `1 − quality`)
- a "home" device ID and IP address, reused by most (not all) of that customer's transactions

### Case → customer assignment

Cases are **not** assigned a customer uniformly at random. Each case first draws a `scenario_archetype` at the target proportions (35/30/20/15%), then a customer is drawn via **weighted** sampling where the weight is `softmax(bias[archetype] · (quality − 0.5) + noise)`. `strong_legitimate`/`high_value_strong` bias toward higher-quality customers, `weak` biases toward lower-quality customers, `ambiguous` is unbiased — but the noise term means this is a *tendency*, not a rule, so customer quality and case archetype are correlated but overlapping, not collapsed.

### Per-case features

Transaction/auth/fulfillment/communication fields are sampled per case from archetype-conditioned probabilities (a 4-way tier: `strong_legitimate`, `high_value_strong`, `weak`, `ambiguous`, each with its own match/availability probabilities — see the `tier4(...)` calls in the script). `high_value_strong` gets its own (moderately strong, not maximal) authentication/fulfillment tier plus a 3.5–9× amount multiplier, reflecting "high amount, relatively strong evidence" rather than "as strong as strong_legitimate."

Missingness is simulated independently per evidence type (e.g. auth evidence missing ~5–15% of the time; fulfillment evidence missingness varies more by archetype, since a fraudulent/weak case is less likely to have fulfillment data captured at all).

### Latent probability model

For each case:

```
auth_component         = relevance-weighted mean of {three_ds, avs, cvv, device_match, ip_match}
fulfillment_component   = relevance-weighted mean of {delivery_confirmed, tracking_available,
                                                        delivery_address_match, proof_of_delivery}
customer_component      = clip(success_ratio − 0.12·log1p(prior_dispute_count), 0, 1)
evidence_available_frac = fraction of the 16 evidence items marked `available`
reason_baseline          = per-reason-code constant (duplicate_charge > goods_not_received > unauthorized_transaction)
amount_component         = 0.10 · clip(z-score of log(amount), −2, 2)
comms_component           = 0.30·has_comms − 0.45·cancellation_request − 0.25·refund_request

logit = -2.85
        + 3.4·auth_component
        + 3.4·fulfillment_component
        + 1.2·customer_component
        + 0.20·evidence_available_frac
        + reason_baseline
        + amount_component
        + comms_component
        + Normal(0, 0.95)

p = clip(sigmoid(logit), 0.02, 0.98)
favorable_outcome ~ Bernoulli(p)
```

Every term is built from a *sampled feature value*, not the archetype label — the archetype only shapes the distributions those features are drawn from. `relevance`-weighting means auth/fulfillment evidence only pulls the logit hard when it's actually relevant to that case's `reason_code`. The 0.95-sigma Gaussian noise term guarantees overlapping distributions and genuinely ambiguous cases even within one archetype — no feature or feature combination perfectly separates the classes.

At n=50,000, seed=42, this yields (see `data/metadata/generation_summary.json` for exact numbers from the last run):

| Archetype | Target favorable rate | Achieved |
|---|---|---|
| `strong_legitimate` | 85–95% | ~93.7% |
| `weak` | 10–20% | ~18.1% |
| `ambiguous` | 45–60% | ~53.4% |
| `high_value_strong` | 80–90% | ~81.5% |

## Reproducibility

All relative timestamps (`account_created_at`, transaction `created_at`, etc.) are computed from a **fixed anchor instant** (`ANCHOR_NOW` in `generate_dataset.py`), not `datetime.now()`. This was a deliberate fix during development — an earlier version used wall-clock time as the reference point, which meant two runs with the identical seed produced byte-different CSVs (the *values* were statistically identical, but timestamps shifted by the few seconds of execution time between runs), silently breaking checksum-based lock verification. With a fixed anchor, `generate_dataset.py --seed 42 --n-cases 50000` run twice produces byte-identical CSVs — verified via `diff -rq` across full reruns.

Only the run metadata (`generation_summary.json`'s `generated_at`, and the lock's `created_at`) reflect actual wall-clock time — that's expected, they're provenance records of *when the script ran*, not part of the generated data.

## Missingness

Missingness is per-evidence-type, independent of `favorable_outcome` directly (it flows into `evidence_available_frac`, a *minor* logit term, rather than dominating the label). This means Phase 2's evidence-matrix builder will need genuine missing-value handling (not just "if present, always favorable") — matching a real-world evidence pipeline where some signals just weren't captured for a given transaction.

## Split strategy

Split is assigned **per customer** (`assign_splits`: each customer independently gets `train`/`validation`/`test` at 70/15/15 via a single uniform draw), and every case inherits its customer's split. This guarantees no customer's transaction/dispute history crosses a split boundary — the strongest leakage risk for a customer-history-driven model. Because customers vary in how many cases they have, the realized case-level split proportions are close to but not exactly 70/15/15 (at n=50,000: ~70.2% / 14.9% / 14.9%).

## Test-set locking

`scripts/generate_dataset.py --lock`:

1. Requires `data/generated/test/*.csv` to already exist (i.e., generation has run).
2. Refuses to run if `data/locked/test/` already has CSVs in it, unless `--force-relock` is passed.
3. Copies the test CSVs into `data/locked/test/`.
4. Computes a SHA-256 over the concatenation of (filename + file bytes) for every locked CSV, sorted by filename.
5. Writes `data/metadata/locked_test_metadata.json`: `dataset_version`, `schema_version`, `generation_seed`, `n_cases_requested`, `created_at`, per-table `row_counts`, `checksum_sha256`.

`scripts/verify_dataset.py` independently recomputes the checksum and re-checks row counts, expected columns, duplicate IDs, FK referential integrity, and that `favorable_outcome` isn't degenerate (0% or 100%) — a cheap sanity net against a corrupted or accidentally-regenerated lock.

`scripts/load_database.py` only ever reads the `test` split from `data/locked/test/` (never `data/generated/test/`), and only when explicitly requested via `--splits ... test`. The default (`--splits train validation`) never touches rows belonging to `split='test'` in the database, so the normal "regenerate → reload" development loop cannot silently change what Phase 2 will eventually evaluate against.
