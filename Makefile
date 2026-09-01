.PHONY: up down build logs generate lock load load-all verify verify-reference test shell

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
