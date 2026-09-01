# Phase 2 — Risk Engine (LightGBM + Calibration + SHAP)

Phase 2 adds the first real intelligence layer: a **case-level winnability model** that answers

> "Based on the evidence currently available for this dispute, how likely are we to obtain a favorable outcome if we contest it?"

It is explicitly **not** a fraud detector, not a customer risk score, and not a decision engine. It produces a calibrated probability and an explanation; whether contesting is *worth it* (expected recovery vs. contest cost) is Phase 3 and is deliberately not implemented here.

## Architecture

```
      stored dispute
            │
            ▼
   evidence retrieval           (relational: dispute → transaction → customer → evidence)
            │
            ▼
   feature engineering          app/ml/features.py   -> 94 deterministic features
            │
            ▼
   LightGBM winnability model   app/ml/model.py      -> raw probability
            │
            ▼
   probability calibration      app/ml/calibration.py -> calibrated probability
            │
      ┌─────┴──────┐
      ▼            ▼
   SHAP         Risk Score API
 explain.py     POST /cases/{id}/score
```

## Feature categories

94 features, ordered deterministically by `app/ml/features.feature_names()` and persisted in `artifacts/models/feature_schema.json`.

| Group | Count | Examples |
|---|---|---|
| Categorical | 5 | `reason_code`, `payment_method`, `transaction_status`, `avs_result`, `cvv_result` (LightGBM native categoricals; unseen values → sentinel `-1`) |
| Case / transaction | 7 | `dispute_amount`, `transaction_amount_log`, `days_transaction_to_dispute`, `days_dispute_to_deadline`, `transaction_capture_lag_minutes` |
| Authentication | 4 | `three_ds_authenticated`, `avs_match`, `cvv_match`, `billing_shipping_match` |
| Customer history | 8 | `customer_account_age_days`, `customer_previous_*_count`, `customer_success_ratio`, `customer_dispute_ratio` |
| Fulfillment (derived) | 2 | `delivery_before_dispute`, `delivery_lag_days` |
| Per-evidence-type | 48 | for each of the 16 evidence types: `ev_<type>_available`, `ev_<type>_strength`, `ev_<type>_value` |
| Evidence completeness | 20 | `evidence_completeness_ratio`, `strong_evidence_count`, `high_relevance_completeness_ratio`, per-category strength means and presence flags |

Three deliberate representation choices:

- **Missing evidence is `NaN`, not `0`.** LightGBM handles NaN natively as "missing", which is semantically different from "present but negative". Keeping `_available` as a separate flag lets the model distinguish *"we have no proof of delivery"* from *"we checked and delivery was not confirmed"* — a distinction that matters enormously to a merchant deciding whether to gather more evidence.
- **Evidence relevance comes from the data, not from a hard-coded map.** The `relevance` column on each evidence row (high/medium/low, which Phase 1 assigns per reason code) drives the `high_relevance_*` aggregates, so the model gets reason-code-aware evidence weighting without the ML layer importing anything from the synthetic generator.
- **`delivery_timestamp` becomes a lag, not a date.** The raw evidence value is an absolute timestamp; feeding an absolute date to a tree model invites calendar overfitting, so it is converted to `delivery_lag_days` and `delivery_before_dispute`.

## Leakage prevention

This is the part of Phase 2 most worth scrutinizing, so the defenses are layered.

**1. Structural (the primary guarantee).** `build_features()` does not accept the `outcomes` table as a parameter:

```python
def build_features(disputes, transactions, customers, evidence) -> pd.DataFrame
```

The target `favorable_outcome` and its **perfect proxy** `recovery_amount` are therefore physically unreachable from the featurization code path. This matters concretely: in the Phase 1 dataset `recovery_amount` is non-null **if and only if** `favorable_outcome` is True (verified — the crosstab is exactly diagonal), so a single careless join would produce a meaningless 1.00 AUC. Labels are only ever produced by the separate `extract_target()` function.

**2. Allowlist, not blacklist.** `schema.ALLOWED_SOURCE_COLUMNS` names exactly which raw columns may be read from each table; the builder slices inputs down to that set before doing anything else. A new upstream column cannot silently become a feature. `test_extra_input_columns_are_ignored` proves this.

**3. Forbidden-column registry.** `schema.FORBIDDEN_COLUMNS` records every excluded column *with its reason*, and the builder raises if any survives into the matrix. Excluded, and why:

| Column | Why excluded |
|---|---|
| `favorable_outcome`, `recovery_amount`, `outcome_at`, `outcome_source` | the target and post-outcome information |
| `scenario_archetype` | synthetic-generator label; unknowable for a real incoming dispute |
| `split` | data-management field |
| `dispute_id`, `transaction_id`, `customer_id`, `evidence_id` | identifiers; `customer_id` is also the split key, so it would enable memorization |
| `merchant_id` | uniformly random in the generator — zero signal by construction; including it would only add variance |
| `device_id`, `ip_address`, `billing_address_id`, `shipping_address_id` | raw identifiers; used only via derived comparisons (`device_match`, `ip_match`, `billing_shipping_match`) |
| `country` | national-origin proxy — excluded on **fairness** grounds (and carries no signal by construction) |
| `disputes.status` | workflow state (`closed`, `under_review`, …) that in production correlates with post-decision information |
| `currency`, `account_created_at` | zero variance / redundant with `account_age_days` |

**4. Temporal discipline on customer history.** Customer-history features come *only* from the `customers` table's `previous_*` columns, which are as-of-account-state attributes recorded before the dispute. We deliberately do **not** compute customer aggregates by counting that customer's other rows in the dataset, for two reasons: a customer's other disputes may occur *after* the one being scored (future leakage), and aggregating their outcomes would touch the target directly. Notably, the spec's suggested `customer_previous_favorable_outcomes` feature was **rejected for exactly this reason** — it is not implemented.

**5. Empirical verification.** `scripts/audit_model_data.py` and `tests/test_ml_leakage.py` assert that no feature correlates with the target at |r| ≥ 0.95, and that injecting outcome columns into the *input* frames still yields a clean matrix. The strongest legitimate correlation observed is `strong_evidence_count` at r = +0.66 — real signal, not a leak.

## Split integrity

Phase 1's customer-level 70/15/15 split is preserved exactly; Phase 2 never reshuffles or re-splits. Verified disjoint at customer, transaction, and dispute level across all three pairs (`test_customer_disjointness`, and the audit script).

Within training, validation is bisected further — **customer-disjointly**, via a stable SHA-256 hash of `customer_id`:

| Data | Used for |
|---|---|
| `train` (35,115) | model fitting only |
| `val_a` (3,752) | early stopping + hyperparameter selection |
| `val_b` (3,687) | calibration fitting/selection, threshold selection, reported validation metrics |
| **locked test (7,446)** | **final evaluation only — never read during training** |

This separation means the data used to pick hyperparameters is disjoint from the data used to fit calibration and choose the operating threshold, so neither decision contaminates the other.

## Model choice

LightGBM is the right tool here: the feature matrix is tabular, mixed-type (numeric + native categoricals), and — importantly — full of structured missingness that LightGBM handles natively without imputation. Gradient-boosted trees are also strong on the interaction effects that dominate this problem (evidence type × reason code), and TreeSHAP gives *exact*, fast attributions rather than the sampled approximations a neural model would require. The chosen configuration is regularization-leaning (`num_leaves=31`, `min_data_in_leaf=200`, `lambda_l2=10.0`, `feature_fraction=0.7`, 212 rounds at `learning_rate=0.03`), selected from a deliberately small 4-config search — this is a risk engine, not a leaderboard entry.

## Calibration

A raw tree-model score ranks well but is not automatically a trustworthy probability. Because Phase 3 will compare this number against monetary quantities, it has to mean what it says: among cases scored 0.70, roughly 70% should actually be won.

Method selection used **cross-fitted calibration within `val_b`** (2 customer-disjoint folds), scored by out-of-fold Brier:

| Method | OOF Brier | OOF ECE |
|---|---|---|
| **sigmoid (Platt)** — chosen | 0.12073 | **0.00922** |
| isotonic | 0.12138 | 0.01079 |
| uncalibrated | **0.12068** | 0.01148 |

**Honest reading of this table:** LightGBM trained with binary logloss is *already* close to calibrated on this data — sigmoid calibration does not improve Brier score (0.12073 vs. 0.12068, a rounding-level difference) and its benefit is confined to a ~20% reduction in Expected Calibration Error (0.0115 → 0.0092). We ship the sigmoid calibrator because it is the best of the three on the selection criterion, because it costs nothing at inference, and because it gives Phase 3 an explicit, inspectable, monitorable surface to recalibrate against real outcomes later. But it would be dishonest to claim calibration "fixed" a miscalibrated model here — it did not, because the model was not badly miscalibrated to begin with. The reliability curve (`make evaluate-calibration`) is close to the diagonal in both cases.

Calibrators serialize to plain JSON rather than pickle, so an artifact stays inspectable, diffable, and portable across library versions.

## Explainability

SHAP answers the merchant-facing question the pitch depends on: *why* is this case considered winnable? `app/ml/explain.py` uses `shap.TreeExplainer` for exact TreeSHAP attributions, cross-checked in tests against LightGBM's own `pred_contrib` output (`test_shap_matches_lightgbm_native_contributions`) to prove nothing is being approximated or fabricated.

Attributions are then mapped to merchant-readable language by `describe_feature(name, value)`, which selects phrasing **from the actual feature value**, so a description can never contradict the case data:

- `three_ds_authenticated = 1` → "The transaction was authenticated with 3-D Secure."
- `ev_proof_of_delivery_value = NaN` → "No proof of delivery evidence is on file."

No LLM is involved in this phase; the mapping is a deterministic lookup.

**Units caveat:** SHAP contributions are in the model's raw margin (log-odds) space, not probability space. A contribution of +0.5 means the feature pushed the log-odds up by 0.5. They should be presented as relative drivers, not additive percentage points — the API schema documents this.

## Evaluation

`train` fits, `validation` decides, the locked test set is read **once** for the official number. `scripts/evaluate_locked_test.py` verifies the locked checksum *before* evaluating (refusing to run on a drifted set) and *again after*, proving nothing was mutated. It never retrains, refits calibration, or re-tunes the threshold.

Operating threshold **0.44**, selected by F1-maximization on out-of-fold calibrated probabilities from `val_b` — never on the test set.

### Results (calibrated, threshold 0.44)

| Metric | Validation (OOF) | **Locked test** |
|---|---|---|
| ROC-AUC | 0.8996 | **0.8990** |
| PR-AUC | 0.9290 | **0.9334** |
| Precision | 0.8593 | **0.8589** |
| Recall | 0.8766 | **0.8705** |
| F1 | 0.8679 | **0.8647** |
| Brier | 0.1207 | **0.1217** |
| ECE | 0.0092 | **0.0122** |
| FPR | — | **0.2333** |
| FNR | — | **0.1295** |

Validation and locked-test numbers agree to within ~0.003 ROC-AUC, which is the main evidence that the model is not overfit.

### Baseline comparison

The baseline is evidence completeness — the heuristic a merchant would use anyway. Three variants are computed and the **strongest** is reported, deliberately, so the comparison is not rigged:

| On locked test | ROC-AUC | PR-AUC | F1 | Brier |
|---|---|---|---|---|
| overall completeness | 0.7185 | 0.7689 | 0.7655 | 0.2505 |
| high-relevance completeness | 0.5553 | 0.6497 | 0.7672 | 0.2957 |
| **high-relevance strength (strongest)** | 0.7579 | 0.7987 | 0.7715 | 0.2094 |
| **Model (calibrated)** | **0.8990** | **0.9334** | **0.8647** | **0.1217** |
| *Model advantage* | *+0.141* | *+0.135* | *+0.093* | *−0.088* |

The model adds ~14 points of ROC-AUC and nearly halves the Brier score over the best honest heuristic. Note the naive "count how much evidence exists" baseline is *worse* than the strength-weighted one — quantity of evidence matters less than whether it is favorable, which is itself a useful finding.

## Error analysis (honest findings)

From `scripts/error_analysis.py` (validation split; the locked-test breakdown is consistent):

**By reason code** — performance is stable (AUC 0.88–0.90 across all three), so nothing collapses for a particular dispute type. `unauthorized_transaction` has the lowest FPR (0.16) but highest FNR (0.17); `duplicate_charge` is the opposite (FPR 0.34, FNR 0.10).

**By archetype** — within-archetype AUC (0.67–0.78) is markedly *lower* than the overall 0.90. This is a Simpson-style effect worth stating plainly: a substantial part of headline AUC comes from separating easy archetypes from hard ones, not from fine discrimination *within* a difficulty tier. Any claim about the model should be read with that in mind.

**Missing evidence systematically hurts recall.** At ≤50% evidence completeness, FNR rises to 0.52 (recall 0.48); above 85% completeness FNR falls to 0.04. The model is appropriately conservative when it cannot see enough — but this means genuinely winnable cases with thin evidence *will* be under-scored. Operationally this is the actionable insight: for low-completeness cases, gather more evidence before trusting a low score.

**Where it is wrong:**
- *False positives* (wrongly called winnable) look almost like true positives — mean evidence strength 0.50 vs. 0.59, 3-DS present 55% vs. 75%. They are genuinely strong-looking cases that happened to lose, which is expected given Phase 1's probabilistic label generation.
- *False negatives* (winnable cases wrongly rejected) have visibly thin evidence — completeness 0.76 and 3-DS present only 13%. They lose despite weak evidence being on file.
- On `strong_legitimate` cases the FPR is 1.00, but the base rate there is 93.9% — with so few true negatives the model calls nearly everything winnable. Worth stating rather than hiding.

## Fairness

No protected attributes are used. `country` is excluded specifically as a national-origin proxy (documented in `FORBIDDEN_COLUMNS` and asserted by `test_protected_attribute_is_excluded`). No race, religion, gender, ethnicity, or age data exists anywhere in the schema. The model relies on transaction, authentication, fulfillment, customer *behavioral* history, dispute reason, and available evidence.

## Determinism

Seeds are fixed for Python `random`, NumPy, and LightGBM (`seed`/`bagging_seed`/`feature_fraction_seed`/`data_random_seed`), with `deterministic=True`, `force_row_wise=True`, and a pinned thread count. Verified empirically: running `scripts/train_model.py` twice produces a **byte-identical** `risk_model.txt` and identical metrics. Feature ordering is persisted, and predictions align by column name rather than position (`test_prediction_independent_of_column_order`).

## Limitations

Stated plainly — this model is **not production-ready**:

1. **The training data is synthetic.** Outcomes were sampled from a latent logistic model we wrote ourselves (see docs/phase1.md). The model has, to a real extent, learned to recover the generator's own structure. Performance on real chargeback data is unknown and would very likely be lower.
2. **The labels are simulated, not observed.** No real issuer ever adjudicated any of these disputes. `favorable_outcome` is a Bernoulli draw, not a recorded fact.
3. **Domain shift is unmeasured.** No external real-world benchmark exists in this project (see docs/external_data.md for why none could be responsibly obtained), so we cannot quantify the synthetic-to-real gap.
4. **Calibration is calibrated to synthetic outcomes.** The reliability curve is excellent *against our own generator*. Against real issuer decisions it would need refitting on observed outcomes.
5. **Within-tier discrimination is weaker than headline AUC suggests** (see error analysis) — 0.90 overall vs. 0.67–0.78 within archetype.
6. **Thin-evidence cases are systematically under-scored** (FNR 0.52 at ≤50% completeness).
7. **No economic reasoning.** A high probability is not a recommendation to contest; expected recovery vs. contest cost is Phase 3.
8. **Risk-band thresholds (0.70 / 0.40) are illustrative, not optimized.** They are presentation buckets, not economically derived cutoffs.

## Phase 2 boundary

Implemented: LightGBM winnability model, probability calibration, SHAP explainability, real `POST /cases/{id}/score`.

**Not** implemented (later phases): decision engine, expected-value contest logic, thresholds tied to money, RAG, embeddings, vector database, LLM drafting, automatic submission, frontend. `POST /cases/{id}/decision` and `POST /cases/{id}/draft` remain deliberate 501 stubs.
