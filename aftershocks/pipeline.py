"""Spark SQL + MLlib pipeline. No synthetic data is used in the dashboard."""

import argparse
import hashlib
import json
import math
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import numpy as np
from pyspark.ml.clustering import KMeans
from pyspark.ml.feature import Normalizer, VectorAssembler
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

from aftershocks.catalog import EVENTS

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = T.StructType(
    [
        T.StructField("event_id", T.StringType(), False),
        T.StructField("article", T.StringType(), False),
        T.StructField("category", T.StringType(), False),
        T.StructField("date", T.StringType(), False),
        T.StructField("views", T.LongType(), False),
    ]
)


def spark_session(master=None):
    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    spark = (
        SparkSession.builder.appName("CuriosityAftershocks")
        .master(master or os.environ.get("SPARK_MASTER", "local[2]"))
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.driver.memory", "1g")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def score_observations(frame, event_dates):
    """Compute pre-event-only baselines; never fit a baseline on the event response."""
    data = frame.withColumn("date", F.to_date("date")).join(F.broadcast(event_dates), "event_id")
    data = data.withColumn("day", F.datediff("date", "event_date"))
    baseline = (
        data.filter(F.col("day") < 0)
        .groupBy("event_id", "article")
        .agg(
            F.avg("views").alias("baseline"),
            F.stddev_pop("views").alias("std"),
            F.count("views").alias("baseline_days"),
        )
    )
    return (
        data.join(baseline, ["event_id", "article"])
        .withColumn("lift", F.col("views") / F.greatest(F.col("baseline"), F.lit(1.0)))
        .withColumn(
            "z",
            (F.col("views") - F.col("baseline"))
            / F.greatest(F.col("std"), F.sqrt(F.col("baseline")), F.lit(1.0)),
        )
        .withColumn("excess", F.greatest(F.col("views") - F.col("baseline"), F.lit(0.0)))
    )


def lagged_edges(topics, threshold=0.72, max_lag=5):
    """Bounded exploratory correlations; arrows mean a best-fit lag, never user movement."""
    edges = []
    relevant = [t for t in topics if t["category"] != "Control"][:40]
    for i, a in enumerate(relevant):
        for b in relevant[i + 1 :]:
            av = np.log1p([v["views"] for v in a["series"] if v["day"] >= 0])
            bv = np.log1p([v["views"] for v in b["series"] if v["day"] >= 0])
            best = None
            for lag in range(-max_lag, max_lag + 1):
                x, y = (av[:lag], bv[-lag:]) if lag < 0 else ((av[lag:], bv[:-lag]) if lag > 0 else (av, bv))
                if len(x) < 7 or np.std(x) < 1e-8 or np.std(y) < 1e-8:
                    continue
                corr = float(np.corrcoef(x, y)[0, 1])
                if math.isfinite(corr) and (best is None or corr > best[0]):
                    best = (corr, lag)
            if best and best[0] >= threshold:
                corr, lag = best
                source, target = (b["id"], a["id"]) if lag > 0 else (a["id"], b["id"])
                edges.append(
                    {"source": source, "target": target, "correlation": round(corr, 4), "lag": abs(lag)}
                )
    return sorted(edges, key=lambda e: -e["correlation"])


def run(raw=ROOT / "data/raw", output=ROOT / "data/processed", master=None):
    started = time.perf_counter()
    manifest = json.loads((raw / "manifest.json").read_text())
    actual_hash = hashlib.sha256((raw / "pageviews.jsonl").read_bytes()).hexdigest()
    if actual_hash != manifest["sha256"]:
        raise ValueError("Source checksum differs from manifest; rerun ingestion")
    spark = spark_session(master)
    output.mkdir(parents=True, exist_ok=True)
    try:
        frame = spark.read.schema(SCHEMA).json(str(raw / "pageviews.jsonl"))
        records = frame.count()
        invalid = frame.filter(
            "views IS NULL OR views < 0 OR article IS NULL OR event_id IS NULL OR try_cast(date as date) IS NULL"
        ).count()
        if invalid:
            raise ValueError(f"{invalid} invalid observations; pipeline aborted")
        if records != frame.dropDuplicates(["event_id", "article", "date"]).count():
            raise ValueError("Duplicate observations; pipeline aborted")
        expected_pairs = {(e["id"], unquote(t)) for e in EVENTS for t in e["topics"]}
        coverage = frame.groupBy("event_id", "article").agg(F.count("*").alias("n")).collect()
        if {(r.event_id, r.article) for r in coverage} != expected_pairs or any(r.n != 50 for r in coverage):
            raise ValueError("Expected all configured topics with exactly 50 daily observations")
        dates = spark.createDataFrame([(e["id"], e["date"]) for e in EVENTS], ["event_id", "event_date"])
        scored = score_observations(frame, dates).cache()
        if scored.filter("day < -28 OR day > 21").count():
            raise ValueError("Observation dates fall outside the configured event window")
        scored.write.mode("overwrite").partitionBy("event_id").parquet(str(output / "silver"))
        post = scored.filter("day >= 0")
        summary = post.groupBy("event_id", "article", "category").agg(
            F.first("baseline").alias("baseline"),
            F.sum("views").alias("total_views"),
            F.sum("excess").alias("excess_views"),
            F.max("lift").alias("peak_lift"),
            F.max("z").alias("peak_z"),
            F.sum(F.when(F.col("z") >= 3, 1).otherwise(0)).alias("burst_days"),
        )
        peaks = (
            post.withColumn(
                "rank",
                F.row_number().over(
                    Window.partitionBy("event_id", "article").orderBy(F.desc("views"), F.asc("day"))
                ),
            )
            .filter("rank = 1")
            .select("event_id", "article", F.col("day").alias("peak_day"))
        )
        summary = summary.join(peaks, ["event_id", "article"])
        # Distributed temporal-shape features; clustering is fitted across all curated topics/events.
        features = (
            post.groupBy("event_id", "article")
            .pivot("day", list(range(22)))
            .agg(F.first(F.log1p("lift")))
            .fillna(0)
        )
        assembled = VectorAssembler(
            inputCols=[str(i) for i in range(22)], outputCol="raw_features"
        ).transform(features)
        normalized = Normalizer(inputCol="raw_features", outputCol="features").transform(assembled)
        model = KMeans(k=4, seed=42, maxIter=30, featuresCol="features", predictionCol="cluster").fit(
            normalized
        )
        assignments = model.transform(normalized).select("event_id", "article", "cluster")
        summary = summary.join(assignments, ["event_id", "article"])
        summary.write.mode("overwrite").partitionBy("event_id").parquet(str(output / "gold_topics"))
        # An honest held-out baseline check, not invented anomaly ground truth.
        train = (
            scored.filter("day < -7").groupBy("event_id", "article").agg(F.avg("views").alias("prediction"))
        )
        holdout = scored.filter("day >= -7 AND day < 0").join(train, ["event_id", "article"])
        eval_rows = (
            holdout.groupBy("event_id")
            .agg(
                F.avg(F.abs(F.col("views") - F.col("prediction"))).alias("mae"),
                (
                    F.sum(F.abs(F.col("views") - F.col("prediction"))) / F.greatest(F.sum("views"), F.lit(1))
                ).alias("wape"),
            )
            .collect()
        )
        evaluation = {
            r["event_id"]: {"mae": round(r["mae"], 2), "wape": round(r["wape"], 4)} for r in eval_rows
        }
        rows = scored.orderBy("event_id", "article", "day").collect()  # Bounded curated cohort only.
        series = {}
        for r in rows:
            series.setdefault((r.event_id, r.article), []).append(
                {
                    "date": str(r.date),
                    "day": r.day,
                    "views": r.views,
                    "lift": round(r.lift, 3),
                    "z": round(r.z, 3),
                }
            )
        summaries = summary.collect()
        events = []
        for event in EVENTS:
            topics = []
            for r in summaries:
                if r.event_id != event["id"]:
                    continue
                topics.append(
                    {
                        "id": r.article,
                        "title": r.article.replace("_", " "),
                        "category": r.category,
                        "baseline": round(r.baseline, 2),
                        "totalViews": r.total_views,
                        "excessViews": round(r.excess_views),
                        "peakLift": round(r.peak_lift, 2),
                        "peakZ": round(r.peak_z, 2),
                        "peakDay": r.peak_day,
                        "burstDays": r.burst_days,
                        "cluster": r.cluster,
                        "series": series[(r.event_id, r.article)],
                    }
                )
            topics.sort(key=lambda t: -t["excessViews"])
            timeline = [
                {
                    "day": day,
                    "date": topics[0]["series"][day + 28]["date"],
                    "views": sum(t["series"][day + 28]["views"] for t in topics),
                    "baseline": round(sum(t["baseline"] for t in topics)),
                }
                for day in range(-28, 22)
            ]
            events.append(
                {
                    **{k: v for k, v in event.items() if k != "topics"},
                    "topics": topics,
                    "edges": lagged_edges(topics),
                    "timeline": timeline,
                    "evaluation": evaluation[event["id"]],
                    "stats": {
                        "totalViews": sum(t["totalViews"] for t in topics),
                        "excessViews": sum(t["excessViews"] for t in topics),
                        "peakLift": max(t["peakLift"] for t in topics),
                        "topics": len(topics),
                    },
                }
            )
        elapsed = time.perf_counter() - started
        payload = {
            "events": events,
            "pipeline": {
                "engine": f"Apache Spark {spark.version}",
                "master": spark.sparkContext.master,
                "records": records,
                "invalidRecords": invalid,
                "durationSeconds": round(elapsed, 2),
                "recordsPerSecond": round(records / elapsed, 1),
                "builtAt": datetime.now(UTC).isoformat(),
                "partitions": 4,
                "clustering": "Spark MLlib KMeans · k=4 · L2-normalized log(1 + lift) · seed=42",
                "source": manifest,
                "granularity": "daily",
                "dataMode": "Real Wikimedia observations",
                "limitations": [
                    "Curated English-language cohort; not a census of public attention.",
                    "Correlation and lag do not establish causality or individual browsing paths.",
                    "Pre-event anticipation can raise the baseline, especially for scheduled events.",
                    "Daily counts cannot resolve hourly aftershocks; missing observations are rejected.",
                    "Lag search is exploratory and not corrected for multiple comparisons.",
                ],
            },
        }
        temp = output / "dashboard.tmp"
        temp.write_text(json.dumps(payload, indent=2, allow_nan=False))
        temp.replace(output / "dashboard.json")
        print(f"Published {records:,} observations · {len(events)} events · {elapsed:.1f}s")
    finally:
        spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--master", default=None)
    args = parser.parse_args()
    run(args.raw, args.output, args.master)
