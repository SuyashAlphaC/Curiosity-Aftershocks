"""Real hourly dump ingestion: Wikimedia gzip → Spark SQL → partitioned Parquet."""

import argparse
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pyspark import StorageLevel
from pyspark.sql import functions as F

from aftershocks.ingest import ROOT, USER_AGENT
from aftershocks.pipeline import spark_session


def download_hour(day, hour, directory):
    parsed = datetime.strptime(day, "%Y-%m-%d")
    if not 0 <= hour <= 23:
        raise ValueError("hour must be in 0..23")
    name = f"pageviews-{parsed:%Y%m%d}-{hour:02d}0000.gz"
    url = f"https://dumps.wikimedia.org/other/pageviews/{parsed:%Y}/{parsed:%Y-%m}/{name}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    if not path.exists():
        tmp = path.with_suffix(".part")
        try:
            with httpx.stream(
                "GET", url, headers={"User-Agent": USER_AGENT}, timeout=120, follow_redirects=True
            ) as response:
                response.raise_for_status()
                with tmp.open("wb") as out:
                    for chunk in response.iter_bytes(1024 * 1024):
                        out.write(chunk)
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    return {"url": url, "file": path.name, "bytes": path.stat().st_size, "sha256": digest}


def parse_dump(lines):
    parts = F.split(F.trim(F.col("value")), r"\s+")
    return (
        lines.withColumn("parts", parts)
        .withColumn("project", F.get("parts", 0))
        .withColumn("article", F.get("parts", 1))
        .withColumn("views", F.get("parts", 2).try_cast("long"))
        .withColumn("response_bytes", F.get("parts", 3).try_cast("long"))
        .withColumn(
            "valid",
            (F.size("parts") == 4)
            & F.col("views").isNotNull()
            & (F.col("views") >= 0)
            & F.col("response_bytes").isNotNull()
            & (F.col("response_bytes") >= 0),
        )
    )


def run(paths, output, master=None):
    started = time.perf_counter()
    spark = spark_session(master)
    spark.conf.set("spark.sql.shuffle.partitions", "16")
    output.mkdir(parents=True, exist_ok=True)
    try:
        if not paths or any(not re.fullmatch(r"pageviews-\d{8}-\d{6}\.gz", p.name) for p in paths):
            raise ValueError("Expected Wikimedia filenames: pageviews-YYYYMMDD-HH0000.gz")
        raw = spark.read.text([str(p.resolve()) for p in paths]).withColumn("file", F.input_file_name())
        parsed = (
            parse_dump(raw)
            .withColumn("hour", F.regexp_extract("file", r"pageviews-(\d{8}-\d{6})", 1))
            .persist(StorageLevel.DISK_ONLY)
        )
        counts = parsed.agg(
            F.count("*").alias("total"), F.sum(F.when(F.col("valid"), 1).otherwise(0)).alias("valid")
        ).first()
        valid = counts.valid or 0
        rejected = counts.total - valid
        # Keep all projects at bronze; filter en/en.m for consistent hourly desktop+mobile counts.
        clean = parsed.filter("valid").select("project", "article", "views", "response_bytes", "hour")
        clean.repartition(16).write.mode("overwrite").partitionBy("hour").parquet(str(output / "bulk_bronze"))
        bronze = spark.read.parquet(str(output / "bulk_bronze"))
        english = (
            bronze.filter(F.col("project").isin("en", "en.m"))
            .repartition(16, "article")
            .groupBy("hour", "article")
            .agg(F.sum("views").alias("views"))
        )
        english.write.mode("overwrite").partitionBy("hour").parquet(str(output / "bulk_english"))
        top = (
            spark.read.parquet(str(output / "bulk_english"))
            .groupBy("article")
            .agg(F.sum("views").alias("views"))
            .orderBy(F.desc("views"))
            .limit(20)
            .collect()
        )
        if rejected:
            parsed.filter(~F.coalesce(F.col("valid"), F.lit(False))).select("value", "file").write.mode(
                "overwrite"
            ).json(str(output / "bulk_rejected"))
        elapsed = time.perf_counter() - started
        report = {
            "engine": f"Apache Spark {spark.version}",
            "records": counts.total,
            "validRecords": valid,
            "rejectedRecords": rejected,
            "durationSeconds": round(elapsed, 2),
            "recordsPerSecond": round(counts.total / elapsed),
            "inputBytes": sum(p.stat().st_size for p in paths),
            "files": [p.name for p in paths],
            "builtAt": datetime.now(UTC).isoformat(),
            "topArticles": [r.asDict() for r in top],
            "granularity": "hourly",
            "note": "Hourly dumps include automated traffic; not interchangeable with API agent=user daily series.",
        }
        tmp = output / "bulk-report.tmp"
        tmp.write_text(json.dumps(report, indent=2))
        tmp.replace(output / "bulk-report.json")
        print(json.dumps(report, indent=2))
    finally:
        spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="2024-04-08")
    parser.add_argument("--hours", type=int, nargs="+", default=[18])
    parser.add_argument("--input", type=Path, nargs="+", help="Existing hourly .gz files; skip downloading")
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--master")
    args = parser.parse_args()
    if args.input:
        paths = args.input
    else:
        folder = ROOT / "data/raw/hourly"
        sources = [download_hour(args.date, hour, folder) for hour in sorted(set(args.hours))]
        (folder / "manifest.json").write_text(json.dumps(sources, indent=2))
        paths = [folder / s["file"] for s in sources]
    run(paths, args.output, args.master)
