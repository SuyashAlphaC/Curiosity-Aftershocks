"""Download free Wikimedia observations with cache, retries and provenance."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, unquote

from aftershocks.catalog import EVENTS

ROOT = Path(__file__).resolve().parents[1]
API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
USER_AGENT = os.environ.get(
    "WIKIMEDIA_USER_AGENT",
    "CuriosityAftershocks/1.0 (local educational research; Wikimedia pageview analysis)",
)


def retry_delay(headers, attempt):
    delay = 120 * (attempt + 1)
    for line in headers.splitlines():
        if line.lower().startswith("retry-after:"):
            value = line.split(":", 1)[1].strip()
            try:
                required = float(value)
            except ValueError:
                try:
                    required = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
                except (TypeError, ValueError):
                    continue
            delay = max(delay, required)
    return delay


def fetch_topic(event, encoded_title, output):
    title = unquote(encoded_title)
    day = date.fromisoformat(event["date"])
    start, end = day - timedelta(days=28), day + timedelta(days=21)
    url = f"{API}/en.wikipedia/all-access/user/{quote(title, safe='')}/daily/{start:%Y%m%d}00/{end:%Y%m%d}00"
    key = hashlib.sha256(url.encode()).hexdigest()[:20]
    cache = output / "responses" / f"{key}.json"
    if cache.exists():
        payload = json.loads(cache.read_text())
    else:
        for attempt in range(5):
            time.sleep(7)
            with tempfile.NamedTemporaryFile() as headers_file:
                response = subprocess.run(
                    [
                        "curl",
                        "--silent",
                        "--show-error",
                        "--location",
                        "--max-time",
                        "60",
                        "--user-agent",
                        USER_AGENT,
                        "--dump-header",
                        headers_file.name,
                        "--write-out",
                        "\n%{http_code}",
                        url,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                headers = Path(headers_file.name).read_text()
            body, _, code = response.stdout.rpartition("\n")
            if response.returncode == 0 and code == "200":
                payload = json.loads(body)
                temp = cache.with_suffix(".tmp")
                temp.write_text(json.dumps(payload))
                temp.replace(cache)
                break
            if code in ("403", "404"):
                raise ValueError(f"HTTP {code} for {title}: {body[:250]}")
            if attempt == 4:
                raise ValueError(f"HTTP {code} for {title} after retries: {response.stderr or body[:250]}")
            delay = retry_delay(headers, attempt) if code in ("429", "503") else 5 * (attempt + 1)
            print(f"  HTTP {code} for {title}; waiting {delay}s before retry", flush=True)
            time.sleep(delay)
    items = payload.get("items", [])
    if not items:
        raise ValueError(f"No observations returned for {title}; refusing synthetic fallback")
    rows = [
        {
            "event_id": event["id"],
            "article": title,
            "category": event["topics"][encoded_title],
            "date": f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}",
            "views": i["views"],
        }
        for i in items
    ]
    expected = (end - start).days + 1
    # Missing days must not silently become zero observations.
    if len({r["date"] for r in rows}) != expected:
        raise ValueError(f"Incomplete series for {title}: expected {expected} days, received {len(rows)}")
    print(f"  {event['id']:8} {title}: {len(rows)} days", flush=True)
    return rows, {
        "event_id": event["id"],
        "article": title,
        "url": url,
        "records": len(rows),
        "fetched_at": datetime.fromtimestamp(cache.stat().st_mtime, UTC).isoformat(),
        "response_sha256": hashlib.sha256(cache.read_bytes()).hexdigest(),
    }


def ingest(output=ROOT / "data/raw"):
    output.mkdir(parents=True, exist_ok=True)
    (output / "responses").mkdir(exist_ok=True)
    jobs = [(event, title, output) for event in EVENTS for title in event["topics"]]
    results, failures = [], []
    for job in jobs:
        try:
            results.append(fetch_topic(*job))
        except (OSError, ValueError) as error:
            failures.append(str(error))
            print(f"  FAILED: {error}", flush=True)
    if failures:
        raise ValueError("Ingestion incomplete; no artifact published:\n" + "\n".join(failures))
    results.sort(key=lambda result: (result[1]["event_id"], result[1]["article"]))
    rows = [row for group, _ in results for row in group]
    path = output / "pageviews.jsonl"
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(row) + "\n" for row in rows))
    tmp.replace(path)
    manifest = {
        "source": "Wikimedia Analytics Pageviews API",
        "license": "CC0",
        "granularity": "daily",
        "project": "en.wikipedia",
        "access": "all-access",
        "agent": "user",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "records": len(rows),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "requests": [metadata for _, metadata in results],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Saved {len(rows):,} genuine observations to {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/raw")
    ingest(parser.parse_args().output)
