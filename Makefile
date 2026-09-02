.PHONY: up down build logs generate lock load load-all verify verify-reference test shell \
        audit train evaluate evaluate-calibration evaluate-locked-test error-analysis model-all \
        evaluate-decisions evaluate-locked-decisions decision-all evaluate-evidence-intel

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f backend

# Regenerate train/validation/test CSVs under data/generated/ (does NOT touch the lock).
generate:
	docker compose run --rm backend python /scripts/generate_dataset.py --seed 42 --n-cases 50000

# Lock the current data/generated/test/ as the frozen held-out benchmark.
# Refuses to run if a lock already exists -- pass FORCE=1 to intentionally re-lock.
lock:
	docker compose run --rm backend python /scripts/generate_dataset.py --seed 42 --n-cases 50000 $(if $(FORCE),--lock --force-relock,--lock)

# Load train+validation into Postgres (safe to rerun any time; never touches locked test rows).
load:
	docker compose run --rm backend python /scripts/load_database.py

# Also load the locked test split (sourced from data/locked/test/, never data/generated/test/).
load-all:
	docker compose run --rm backend python /scripts/load_database.py --splits train validation test

verify:
	docker compose run --rm backend python /scripts/verify_dataset.py

verify-reference:
	docker compose run --rm backend python /scripts/verify_reference_data.py

test:
	docker compose run --rm backend pytest -v

shell:
	docker compose exec backend bash

# ---------------------------------------------------------------------------
# Phase 2 -- risk model (LightGBM + calibration + SHAP)
# ---------------------------------------------------------------------------

# Audit the dataset before modeling. Fails loudly on leakage/split problems.
audit:
	docker compose run --rm backend python /scripts/audit_model_data.py --json-out /artifacts/evaluation/data_audit.json

# Train the model. Deterministic: same data + seed 42 -> byte-identical artifacts.
train:
	docker compose run --rm backend python /scripts/train_model.py

# Validation metrics + evidence-completeness baseline comparison.
evaluate:
	docker compose run --rm backend python /scripts/evaluate_model.py

evaluate-calibration:
	docker compose run --rm backend python /scripts/evaluate_calibration.py

# OFFICIAL final evaluation. Read-only; verifies the locked checksum before and after.
evaluate-locked-test:
	docker compose run --rm backend python /scripts/evaluate_locked_test.py

error-analysis:
	docker compose run --rm backend python /scripts/error_analysis.py

# Full Phase 2 pipeline, in order.
model-all: audit train evaluate evaluate-calibration error-analysis evaluate-locked-test

# ---------------------------------------------------------------------------
# Phase 3 -- cost-sensitive decision engine
# ---------------------------------------------------------------------------

# Decision policy on validation, vs. baselines. Policy is NOT tuned on test.
evaluate-decisions:
	docker compose run --rm backend python /scripts/evaluate_decisions.py

# OFFICIAL final decision evaluation. Read-only; verifies the locked checksum before and after.
evaluate-locked-decisions:
	docker compose run --rm backend python /scripts/evaluate_locked_decisions.py

decision-all: evaluate-decisions evaluate-locked-decisions

# ---------------------------------------------------------------------------
# Phase 4 -- evidence intelligence, grounded RAG, claim-level verification
# ---------------------------------------------------------------------------

# 8-case controlled benchmark: gap-detection accuracy, retrieval relevance,
# grounding rates, blocked-response rate. Deterministic (FakeLLMProvider), no
# API key required.
evaluate-evidence-intel:
	docker compose run --rm backend python /scripts/evaluate_evidence_intel.py
