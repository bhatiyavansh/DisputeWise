# data/external/ — EXTERNAL_BENCHMARK_ONLY area

This directory is reserved for external real-world benchmark datasets, should a suitable one ever be identified. **It is currently empty.**

See [docs/external_data.md](../../docs/external_data.md) for the investigation: what we looked for, what we found, and why nothing was added.

Rules that apply to anything placed here in the future (see `docs/external_data.md` for the full explanation):

- Anything added here MUST be explicitly labeled `EXTERNAL_BENCHMARK_ONLY` in a `manifest.json` alongside it, with full provenance (source, license, retrieval date).
- Nothing here is ever merged into `data/generated/` or `data/locked/test/`.
- Nothing here is used to train or retrain any model.
- Nothing here affects the primary evaluation metrics reported against the locked synthetic test set — it is used only as a separate, clearly-labeled domain-shift benchmark.
