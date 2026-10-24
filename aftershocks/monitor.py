"""Local monitor lifecycle and streaming anomaly calculations."""

import json
import math
import os
import signal
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import numpy as np
from pydantic import BaseModel, Field, field_validator
from pyspark.sql import functions as F

ROOT = Path(__file__).resolve().parents[1]
BASELINE_HOURS = 3


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, indent=2, allow_nan=False))
    temp.replace(path)


class MonitorConfig(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    occurred_at: datetime
    exclude_terms: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("name")
    @classmethod
    def name_is_nonempty(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Enter an event name of at least three characters")
        return value

    @field_validator("occurred_at")
    @classmethod
    def time_is_recent(cls, value):
        if value.tzinfo is None:
            raise ValueError("Event time must include a timezone")
        value = value.astimezone(UTC)
        now = datetime.now(UTC)
        if value > now or value < now - timedelta(hours=24):
            raise ValueError("Choose an event within the past 24 hours, not in the future")
        return value

    @field_validator("exclude_terms")
    @classmethod
    def bounded_terms(cls, values):
        terms = list(dict.fromkeys(v.strip().lower() for v in values if v.strip()))
        if any(len(v) < 3 or len(v) > 50 for v in terms):
            raise ValueError("Headline terms must contain 3–50 characters")
        return terms


def baseline_hours(event_hour):
    return [event_hour - timedelta(hours=i) for i in range(BASELINE_HOURS, 0, -1)]


def anomaly_candidates(baseline, current, exclude_terms):
    """Scan the entire eligible English universe, not a hand-picked topic list."""
    reference = (
        baseline.groupBy("article")
        .agg(
            F.avg("views").alias("baseline"),
            F.stddev_pop("views").alias("std"),
            F.countDistinct("hour").alias("samples"),
        )
        .filter((F.col("samples") == BASELINE_HOURS) & (F.col("baseline") >= 10))
    )
    scored = (
        current.join(reference, "article")
        .withColumn("lift", F.col("views") / F.col("baseline"))
        .withColumn("excess", F.col("views") - F.col("baseline"))
        .withColumn("z", F.col("excess") / F.greatest(F.col("std"), F.sqrt("baseline"), F.lit(1.0)))
    )
    decoded = F.coalesce(F.try_url_decode(F.regexp_replace("article", r"\+", "%2B")), F.col("article"))
    for term in exclude_terms:
        scored = scored.filter(~F.lower(F.regexp_replace(decoded, "_", " ")).contains(term))
    return scored.filter(
        (F.col("views") >= 200) & (F.col("excess") >= 100) & (F.col("lift") >= 3) & (F.col("z") >= 4)
    )


def observed_edges(nodes):
    """Only observed points; never links from future data or event-to-topic causal edges."""
    edges = []
    for i, a in enumerate(nodes):
        for b in nodes[i + 1 :]:
            av = {p["hour"]: p["views"] for p in a["series"] if p["views"] is not None}
            bv = {p["hour"]: p["views"] for p in b["series"] if p["views"] is not None}
            common = sorted(av.keys() & bv.keys())
            if len(common) < 5:
                continue
            x, y = np.log1p([av[h] for h in common]), np.log1p([bv[h] for h in common])
            if np.std(x) < 1e-8 or np.std(y) < 1e-8:
                continue
            correlation = float(np.corrcoef(x, y)[0, 1])
            if math.isfinite(correlation) and correlation >= 0.85:
                edges.append(
                    {
                        "source": a["id"],
                        "target": b["id"],
                        "correlation": round(correlation, 4),
                        "samples": len(common),
                    }
                )
    return edges


class MonitorManager:
    """One owned subprocess per API instance; app shutdown terminates its process group."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.process = None
        self.run = None
        self.lock = threading.RLock()

    def status(self):
        with self.lock:
            pointer = self.directory / "latest.json"
            if self.run is None and pointer.exists():
                self.run = self.directory / "runs" / json.loads(pointer.read_text())["id"]
            if self.run is None:
                return {
                    "active": False,
                    "phase": "idle",
                    "message": "Name an event to start monitoring.",
                    "topics": [],
                    "edges": [],
                    "timeline": [],
                    "log": [],
                }
            path = self.run / "state.json"
            state = json.loads(path.read_text()) if path.exists() else {"phase": "starting"}
            active = self.process is not None and self.process.poll() is None
            state["active"] = active
            if not active and state["phase"] not in ("stopped", "completed", "failed"):
                state.update(
                    phase="interrupted",
                    message="Monitor is not running. Start again to resume with cached data.",
                )
            return state

    def start(self, config):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError("A monitor is already running. Stop it before starting another.")
            run_id = uuid4().hex
            self.run = self.directory / "runs" / run_id
            self.run.mkdir(parents=True)
            atomic_json(self.run / "config.json", config.model_dump(mode="json"))
            atomic_json(
                self.run / "state.json",
                {
                    "phase": "starting",
                    "message": "Starting the Spark monitor…",
                    "config": config.model_dump(mode="json"),
                    "topics": [],
                    "edges": [],
                    "timeline": [],
                    "log": [],
                    "baselineHours": BASELINE_HOURS,
                    "processedHours": 0,
                    "sourceRecords": 0,
                },
            )
            atomic_json(self.directory / "latest.json", {"id": run_id})
            with (self.run / "worker.log").open("a") as log:
                self.process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "aftershocks.live_worker",
                        "--run",
                        str(self.run),
                        "--cache",
                        str(self.directory / "cache"),
                    ],
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            return self.status()

    def stop(self):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait()
            state = self.status()
            if self.run and self.process is not None:
                state.update(
                    phase="stopped",
                    active=False,
                    message="Monitoring stopped. Last observations are retained.",
                )
                atomic_json(self.run / "state.json", state)
            return state
