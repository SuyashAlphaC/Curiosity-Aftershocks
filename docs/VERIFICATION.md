# Verification record

Environment: local Linux workstation, Python 3.12.12, OpenJDK 21.0.9, Node.js 24.5.0, Spark 4.0.1. Verification date: 2026-10-24.

## Full public hourly dump

Command:

```bash
uv run python -m aftershocks.bulk --date 2024-04-08 --hours 18
```

A cached-file rerun verified the final memory-efficient processing path:

```bash
uv run python -m aftershocks.bulk --input data/raw/hourly/pageviews-20240408-180000.gz
```

- Input: `pageviews-20240408-180000.gz`, 66,063,471 bytes compressed.
- Records parsed by Spark: **7,750,691**.
- Valid records: **7,750,691**; rejected: **0**.
- Runtime, including JVM start and Parquet publication, excluding download: **164.53 seconds**.
- Measured throughput: **47,107 records/second**.
- Spark master: `local[2]`; JVM heap: 1 GB; bulk shuffle partitions: 16.
- Complete projects written to `data/processed/bulk_bronze`, English desktop/mobile aggregation to `data/processed/bulk_english`.
- `python3 scripts/audit_bulk.py` independently streamed the original gzip file and confirmed both the total and valid row counts. English desktop/mobile view sum: **12,992,398**.

Evidence: `bulk-report.json`, `bulk-source-manifest.json`, and `bulk-audit.json` in this directory.

The original one-partition aggregate exhausted a 1 GB heap. The verified implementation persists parsed rows on disk, materializes partitioned Parquet, and repartitions by article before aggregation. This preserves the full dataset while bounding the aggregation workload.

## Daily study and application

- `make setup`: passed; locked Python environment and `npm ci` completed. npm audit reported zero known vulnerabilities at installation time.
- `make reproduce`: passed offline from `data/reference`; Spark published all 2,850 genuine observations across three events, then built the production UI. Final measured study runtime: **51.20 seconds**.
- `uv run pytest -q`: **7 passed**. Tests execute real local Spark jobs for baseline/variance and dump-parser cases, plus lag, API, rate-limit, coverage, and generated-artifact checks. A dependency deprecation warning from Starlette's httpx test adapter is non-fatal.
- `uv run ruff check aftershocks tests scripts`: passed.
- Frontend strict TypeScript check + Vite production build: passed.
- `npm --prefix frontend run test:e2e`: **3 passed** in Chromium, covering all three events, graph inspection, replay/pause/reset, search/no-results, controls, sorting, threshold changes, CSV download, research views, mobile layout, keyboard navigation, and service-error retry.
- Additional browser sweep: all three workspace views at **360, 768, 1024, and 1512 px**; no document overflow or uncaught page errors.
- Production UI and API served successfully together on port 8000 during testing.
- `make dev` / `scripts/dev.py`: Vite served on 5173, its API proxy returned ready, and Ctrl+C stopped both owned child process groups.

Screenshots: `observatory.png`, `pipeline.png`, and `mobile.png`. The initial mobile overflow issue was traced to an absolutely positioned table accessibility label and corrected at its scrolling container.

### Reference integrity

The 57 public requests produced 2,850 article/day records. Reference input SHA-256:

```text
577cf418f005568c3653f45250d5266054cfd9f0e00128e115d56bbc7d0905f1
```

The Spark pipeline verifies that hash before processing. It rejects duplicates, invalid counts, wrong observation windows, and incomplete cohorts. The final studies each contain 19 topics and 50 daily points per topic. See `COHORT.md` for coverage-driven title replacements and their selection-bias implications.

### Measured baseline evaluation

| Study | Held-out MAE (views/article/day) | WAPE |
|---|---:|---:|
| Eclipse | 12,385.84 | 75.01% |
| Chandrayaan-3 | 5,723.76 | 59.67% |
| Titan | 582.50 | 23.82% |

These high errors in anticipated events are real results, not hidden failures: the constant pre-event mean is a weak predictor when attention rises ahead of the event. They do not constitute anomaly-detection accuracy or causal evidence.

### Scope of verification

Verified locally on a single machine. No paid services or credentials were used. Multi-node Spark execution, internet availability on another device, and future upstream data changes are not asserted as tested. The bundled CC0 reference observations make the demonstrated daily analytics independent of future API availability.
