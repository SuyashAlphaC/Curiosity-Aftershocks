"""Recent-event watcher: public hourly files → Structured Streaming → discovery graph."""

import argparse
import fcntl
import json
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

import httpx
from pyspark import StorageLevel
from pyspark.sql import functions as F

from aftershocks.bulk import download_hour, parse_dump
from aftershocks.ingest import USER_AGENT, retry_delay
from aftershocks.monitor import anomaly_candidates, atomic_json, baseline_hours, observed_edges
from aftershocks.pipeline import spark_session
from aftershocks.relevance import MAX_CANDIDATES, filter_candidates

POLL_SECONDS = 300


def hour_key(hour):
    return hour.strftime("%Y%m%d-%H0000")


def available_hours(now):
    # Include the previous month when the baseline crosses a month boundary.
    months = {(now - timedelta(days=i)).strftime("%Y/%Y-%m") for i in (0, 2)}
    available = set()
    for month in sorted(months):
        url = f"https://dumps.wikimedia.org/other/pageviews/{month}/"
        response = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=45, follow_redirects=True)
        response.raise_for_status()
        for key in re.findall(r"pageviews-(\d{8}-\d{6})\.gz", response.text):
            hour = datetime.strptime(key, "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
            if hour + timedelta(hours=1) <= now:
                available.add(hour)
    return available


def ingest_hour(spark, source, destination, checkpoint):
    """A real file-source micro-batch; a completed report makes retries idempotent."""
    report_path = destination / "report.json"
    if report_path.exists():
        return json.loads(report_path.read_text())
    started = time.perf_counter()
    key = source.name.removeprefix("pageviews-").removesuffix(".gz")
    # An interrupted callback may have committed a stream offset but not its report.
    # Its single-file checkpoint is disposable until publication is complete.
    if checkpoint.exists():
        shutil.rmtree(checkpoint)

    def publish(batch, _batch_id):
        batch = batch.persist(StorageLevel.DISK_ONLY)
        try:
            source_rows = batch.count()
            english = batch.filter(F.col("value").startswith("en ") | F.col("value").startswith("en.m "))
            parsed = parse_dump(english)
            counts = parsed.agg(
                F.count("*").alias("total"), F.sum(F.when(F.col("valid"), 1).otherwise(0)).alias("valid")
            ).first()
            # Namespace/system traffic is excluded; encoded namespace separators are handled too.
            clean = parsed.filter("valid").filter(
                ~F.regexp_replace("article", "%3[Aa]", ":").contains(":")
                & ~F.col("article").isin("Main_Page", "-", "Special%3ASearch")
            )
            aggregate = (
                clean.select("article", "views")
                .repartition(16, "article")
                .groupBy("article")
                .agg(F.sum("views").alias("views"))
                .withColumn("hour", F.lit(key))
            )
            aggregate.write.mode("overwrite").parquet(str(destination / "parquet"))
            report = {
                "hour": key,
                "sourceRecords": source_rows,
                "englishRecords": counts.total,
                "rejectedEnglishRecords": counts.total - (counts.valid or 0),
                "durationSeconds": round(time.perf_counter() - started, 2),
                "engine": f"Apache Spark {spark.version} Structured Streaming",
                "completedAt": datetime.now(UTC).isoformat(),
            }
            atomic_json(report_path, report)
        finally:
            batch.unpersist()

    stream = spark.readStream.format("text").option("pathGlobFilter", source.name).load(str(source.parent))
    query = (
        stream.writeStream.foreachBatch(publish)
        .option("checkpointLocation", str(checkpoint))
        .trigger(availableNow=True)
        .start()
    )
    query.awaitTermination()
    if not report_path.exists():
        raise ValueError(f"No micro-batch was published for {source.name}")
    return json.loads(report_path.read_text())


def discovery_snapshot(spark, cache, baselines, observed, terms, config):
    def read(hours):
        return spark.read.parquet(*[str(cache / hour_key(h) / "parquet") for h in hours])

    baseline = read(baselines)
    latest = observed[-1]
    current = read([latest])
    eligible = current.count()
    candidates = anomaly_candidates(baseline, current, terms).cache()
    try:
        candidate_count = candidates.count()
        best = candidates.orderBy(F.desc("excess"), F.asc("article")).limit(MAX_CANDIDATES).collect()
    finally:
        candidates.unpersist()
    best, evidence, relevance = filter_candidates(spark, best, config, cache / "article_text")
    ids = [r.article for r in best]
    history = []
    if ids:
        history = read(baselines + observed).filter(F.col("article").isin(ids)).collect()
    points = {(r.article, r.hour): r.views for r in history}
    nodes = [
        {
            "id": r.article,
            "title": unquote(r.article).replace("_", " "),
            "views": r.views,
            "baseline": round(r.baseline, 2),
            "lift": round(r.lift, 2),
            "z": round(r.z, 2),
            "excess": round(r.excess),
            "baselineSamples": r.samples,
            "relevance": evidence[r.article],
            "series": [
                {
                    "hour": hour_key(h),
                    "views": points.get((r.article, hour_key(h))),
                    "baseline": h in baselines,
                }
                for h in baselines + observed
            ],
        }
        for r in best
    ]
    return {
        "topics": nodes,
        "edges": observed_edges(nodes),
        "candidateCount": candidate_count,
        "relatedCount": relevance["accepted"],
        "relevance": relevance,
        "scannedArticles": eligible,
        "latestHour": latest.isoformat(),
        "dataLagMinutes": round((datetime.now(UTC) - latest - timedelta(hours=1)).total_seconds() / 60, 1),
    }


def run_monitor(run, cache, once=False):
    config = json.loads((run / "config.json").read_text())
    event_hour = (
        datetime.fromisoformat(config["occurred_at"])
        .astimezone(UTC)
        .replace(minute=0, second=0, microsecond=0)
    )
    baselines = baseline_hours(event_hour)
    end = event_hour + timedelta(hours=24)
    state_path = run / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    state.update(
        config=config,
        phase="starting",
        topics=[],
        edges=[],
        timeline=[],
        log=[],
        sourceRecords=0,
        processedHours=0,
        baselineHours=len(baselines),
        baselineReady=0,
        eventHour=event_hour.isoformat(),
        pollSeconds=POLL_SECONDS,
        method="3 pre-event hourly samples; views ≥ 200, lift ≥ 3, excess ≥ 100, z ≥ 4. "
        "Graph edges: observed log-count correlation ≥ 0.85 over ≥ 5 shared points.",
        limitations=[
            "Global traffic spikes are candidates, not proven effects of this event.",
            "TF-IDF and required concept matches indicate topical relevance, not event causation.",
            "Only the strongest 300 traffic spikes are checked; low-ranked relevant spikes may be missed.",
            "A short three-hour baseline is sensitive to daily traffic cycles and other concurrent news.",
            "Hourly dumps include automated traffic. New or sparse titles without all baseline samples are excluded.",
            "The event hour may include traffic from before the exact event time.",
        ],
    )
    processed, observed, reports = set(), [], {}

    def update(phase, message, **fields):
        state.update(phase=phase, message=message, updatedAt=datetime.now(UTC).isoformat(), **fields)
        state["log"] = (state["log"] + [{"time": datetime.now(UTC).isoformat(), "message": message}])[-40:]
        atomic_json(state_path, state)
        print(message, flush=True)

    cache.mkdir(parents=True, exist_ok=True)
    spark = None
    lock_handle = None
    try:
        lock_handle = (cache / ".worker.lock").open("a")
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "Another monitor is using this cache. Stop it before starting another."
            ) from None
        update("starting", "Starting Apache Spark Structured Streaming…")
        spark = spark_session()
        spark.conf.set("spark.sql.shuffle.partitions", "16")
        while True:
            now = datetime.now(UTC)
            delay = POLL_SECONDS
            update("checking", "Checking Wikimedia for published hourly dumps…")
            try:
                available = available_hours(now)
                relevant = [
                    event_hour + timedelta(hours=i)
                    for i in range(24)
                    if event_hour + timedelta(hours=i) in available and event_hour + timedelta(hours=i) < end
                ]
                missing_baselines = [h for h in baselines if h not in available and h not in processed]
                ready_baselines = [h for h in baselines if h in available or h in processed]
                for hour in ready_baselines + (relevant if not missing_baselines else []):
                    if hour in processed:
                        continue
                    key = hour_key(hour)
                    destination = cache / key
                    if not (destination / "report.json").exists():
                        update(
                            "downloading",
                            f"Downloading the complete {hour:%b %d, %H:00} UTC dump…",
                            processingHour=hour.isoformat(),
                        )
                        source = download_hour(hour.strftime("%Y-%m-%d"), hour.hour, cache / "downloads")
                        atomic_json(destination / "source.json", source)
                        update(
                            "processing",
                            f"Spark is scanning {source['bytes'] / 1024 / 1024:.1f} MiB for {hour:%H:00} UTC…",
                        )
                        reports[key] = ingest_hour(
                            spark,
                            cache / "downloads" / source["file"],
                            destination,
                            run / "checkpoints" / key,
                        )
                    else:
                        reports[key] = json.loads((destination / "report.json").read_text())
                    processed.add(hour)
                    if hour >= event_hour:
                        observed.append(hour)
                        observed.sort()
                    update(
                        "analyzing",
                        f"Processed {hour:%H:00} UTC; updating the anomaly scan…",
                        processedHours=len(processed),
                        sourceRecords=sum(r["sourceRecords"] for r in reports.values()),
                        baselineReady=sum(h in processed for h in baselines),
                    )
                    if observed:
                        snapshot = discovery_snapshot(
                            spark, cache, baselines, observed, config["exclude_terms"], config
                        )
                        state.update(snapshot)
                        state["timeline"] = [
                            p for p in state["timeline"] if p["hour"] != snapshot["latestHour"]
                        ]
                        state["timeline"].append(
                            {
                                "hour": snapshot["latestHour"],
                                "candidates": snapshot["candidateCount"],
                                "scannedArticles": snapshot["scannedArticles"],
                            }
                        )
                        update(
                            "monitoring",
                            f"{snapshot['relatedCount']} relevant spikes from {snapshot['candidateCount']} traffic spikes; "
                            f"checked the strongest {snapshot['relevance']['checked']} candidates.",
                        )
                update(
                    "monitoring" if observed else "waiting",
                    (
                        (
                            "Waiting for baseline files: "
                            + ", ".join(h.strftime("%H:00 UTC") for h in missing_baselines)
                        )
                        if missing_baselines
                        else "Watching for the next published hour. Next source check in 5 minutes."
                    ),
                    nextCheckAt=(datetime.now(UTC) + timedelta(seconds=POLL_SECONDS)).isoformat(),
                )
                if once or now >= end + timedelta(hours=3):
                    update(
                        "completed", "Scan completed." if once else "The 24-hour monitoring window has ended."
                    )
                    break
            except (httpx.HTTPError, OSError, ValueError, subprocess.SubprocessError) as error:
                if isinstance(error, httpx.HTTPStatusError):
                    delay = max(
                        delay, retry_delay("Retry-After: " + error.response.headers.get("Retry-After", ""), 0)
                    )
                update(
                    "retrying",
                    f"Source/analysis temporarily unavailable: {str(error)[:300]}. Retrying in {round(delay / 60)} minutes.",
                    nextCheckAt=(datetime.now(UTC) + timedelta(seconds=delay)).isoformat(),
                )
                if once:
                    raise
            time.sleep(delay)
    except Exception as error:
        update("failed", f"Monitor failed: {type(error).__name__}: {str(error)[:350]}")
        raise
    finally:
        if spark is not None:
            spark.stop()
        if lock_handle is not None:
            lock_handle.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--once", action="store_true", help="Process currently available hours and exit")
    args = parser.parse_args()
    run_monitor(args.run, args.cache, args.once)
