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


## Recent-event monitor extension

Fresh-data validation on 2026-10-24 used five complete public hourly files: 2026-10-23 23:00 UTC through 2026-10-24 03:00 UTC. The test's 02:00 UTC cutoff is an engineering validation window, not attribution to a named real-world event.

- **29,509,818 source records** ingested through the actual Spark Structured Streaming file source and published as hourly Parquet.
- Three pre-cutoff baseline hours, followed by two observed post-cutoff hours.
- At 02:00 UTC: **107** spike candidates from **1,419,683** English article titles.
- At 03:00 UTC: **174** spike candidates from **1,413,392** English article titles.
- The 24 strongest current candidates produced **158** observed co-movement links (correlation ≥ 0.85; five shared observations).
- No article list was supplied for discovery. Namespace/system titles, incomplete baselines, low traffic and non-bursting observations were excluded.
- Evidence: `live-validation.json` and `live-source-manifest.json`. Source files and full Parquet are in the ignored local monitor cache, not bundled into Git.
- Ten monitor tests passed: timezone/recent-event validation; burst eligibility and noise rejection; minimum graph evidence; an actual Structured Streaming micro-batch and idempotent reuse; owned process lifecycle and duplicate-start rejection; API validation; partial-baseline ingestion without fabrication; cache locking; decoded headline filtering; and avoiding mutation of another API's worker state.
- The seven original analytics/backend tests remain passing. Five browser tests pass, covering the existing application plus monitor configuration, candidate inspection, stopping, independence from historical artifacts, and mobile layout.
- Production frontend build and Python lint passed.

The initial fresh-data warm-up on this connection took approximately 20 minutes for five full files plus analytics. This is why the demo guide recommends starting before presenting. Reusing completed hourly Parquet avoids downloading and ingesting those raw files again. The source itself was several hours behind wall-clock time; the UI explicitly displays that age.


The actual HTTP lifecycle was also exercised: `POST /api/monitor/start` launched a real worker, reused the five completed hourly caches, recomputed both observation frames, and reached a watching state. `POST /api/monitor/stop` terminated the owned worker and retained all 24 nodes / 158 links. Desktop and 390 px mobile screenshots of that actual running watch are saved as `live-monitor.png` and `live-monitor-mobile.png`; the browser reported no uncaught errors or document overflow.

## Event relevance filter (2026-10-26)

- Live candidates now pass a Spark MLlib smoothed TF-IDF cosine filter plus all-required-concept matching before graph selection. The checked pool is the strongest 300 spikes, with up to 24 accepted topics displayed.
- 21 backend/analytics tests pass, including unrelated sports/film rejection, wrong-country protest rejection, missing-description exclusion, a single-document TF-IDF case, metadata failure handling, and a relevant candidate below the original top-24 boundary.
- Five browser tests pass, including submitting event context/required terms and inspecting the relevance explanation. TypeScript/Vite build and Python lint pass.
- Actual Wikimedia lead text/categories were retrieved for six articles: two French-protest topics plus Olivia Newton-John, John Travolta, George Kittle and Brian Brobbey. The topical filter accepted the two protest topics and rejected the four unrelated examples. Exact scores are recorded in `relevance-validation.json`.
- This is a small sanity check, not a labeled accuracy benchmark. Historical protest articles passing this check are not evidence of relevance to the particular October 2026 protest, and are not automatically eligible for the live graph: they must separately pass traffic anomaly rules.
