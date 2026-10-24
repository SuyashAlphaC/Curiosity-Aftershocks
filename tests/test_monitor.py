import gzip
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aftershocks import api
from aftershocks.live_worker import ingest_hour
from aftershocks.monitor import MonitorConfig, MonitorManager, anomaly_candidates, observed_edges
from aftershocks.pipeline import spark_session


@pytest.fixture(scope="module")
def spark():
    session = spark_session("local[2]")
    yield session
    session.stop()


def test_monitor_config_requires_a_recent_aware_event():
    now = datetime.now(UTC)
    assert MonitorConfig(
        name="Test event", occurred_at=now, exclude_terms=[" solar ", "solar"]
    ).exclude_terms == ["solar"]
    for invalid in [now + timedelta(hours=1), now - timedelta(days=2), now.replace(tzinfo=None)]:
        with pytest.raises(ValidationError):
            MonitorConfig(name="Test event", occurred_at=invalid)
    with pytest.raises(ValidationError):
        MonitorConfig(name="   ", occurred_at=now)


def test_discovery_filters_noise_sparse_titles_and_headline_terms(spark):
    rows = []
    for article, values in [
        ("Unexpected_topic", [20, 20, 20]),
        ("Event_news", [20, 20, 20]),
        ("Noisy", [10, 1000, 10]),
        ("Sparse", [20, 20]),
        ("Ordinary", [20, 20, 20]),
    ]:
        rows.extend((article, str(i), value) for i, value in enumerate(values))
    baseline = spark.createDataFrame(rows, ["article", "hour", "views"])
    current = spark.createDataFrame(
        [
            ("Unexpected_topic", "3", 400),
            ("Event_news", "3", 400),
            ("Noisy", "3", 1200),
            ("Sparse", "3", 10000),
            ("Brand_new", "3", 20000),
            ("Ordinary", "3", 25),
        ],
        ["article", "hour", "views"],
    )
    result = anomaly_candidates(baseline, current, ["event"]).collect()
    assert [r.article for r in result] == ["Unexpected_topic"]
    assert result[0].baseline == 20
    assert result[0].lift == 20
    assert result[0].excess == 380


def test_graph_requires_five_shared_observations():
    def node(name, values):
        return {"id": name, "series": [{"hour": str(i), "views": v} for i, v in enumerate(values)]}

    a = node("A", [10, 11, 9, 100, 200])
    b = node("B", [20, 22, 18, 200, 400])
    assert observed_edges([a, node("B", [20, 22, 18, 200])]) == []
    edge = observed_edges([a, b, node("constant", [10] * 5)])[0]
    assert edge["source"] == "A" and edge["target"] == "B"
    assert edge["samples"] == 5 and edge["correlation"] > 0.99
    assert observed_edges([a, node("missing", [20, None, 18, 200, 400])]) == []


def test_actual_structured_streaming_microbatch_is_idempotent(spark, tmp_path):
    inbox = tmp_path / "input"
    inbox.mkdir()
    source = inbox / "pageviews-20261024-000000.gz"
    with gzip.open(source, "wt") as out:
        out.write(
            "en Unexpected_topic 100 0\nen.m Unexpected_topic 50 0\nen Main_Page 10000 0\n"
            "fr Other 200 0\nen Bad bad 0\nen Special:Search 999 0\n"
        )
    destination = tmp_path / "hour"
    checkpoint = tmp_path / "checkpoint"
    first = ingest_hour(spark, source, destination, checkpoint)
    assert first["sourceRecords"] == 6
    assert first["rejectedEnglishRecords"] == 1
    rows = spark.read.parquet(str(destination / "parquet")).collect()
    assert len(rows) == 1 and rows[0].views == 150 and rows[0].article == "Unexpected_topic"
    second = ingest_hour(spark, source, destination, checkpoint)
    assert second == first


def test_owned_process_lifecycle_and_conflict(tmp_path, monkeypatch):
    actual_popen = subprocess.Popen
    monkeypatch.setattr(
        "aftershocks.monitor.subprocess.Popen",
        lambda _cmd, **kwargs: actual_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs),
    )
    manager = MonitorManager(tmp_path)
    config = MonitorConfig(name="Local lifecycle test", occurred_at=datetime.now(UTC))
    assert manager.status()["phase"] == "idle"
    try:
        assert manager.start(config)["active"] is True
        with pytest.raises(RuntimeError, match="already running"):
            manager.start(config)
    finally:
        state = manager.stop()
    assert state["active"] is False and state["phase"] == "stopped"
    assert manager.process.poll() is not None
    restarted = MonitorManager(tmp_path)
    assert restarted.status()["phase"] == "stopped"


def test_monitor_api_validation_and_status(tmp_path, monkeypatch):
    manager = MonitorManager(tmp_path)
    monkeypatch.setattr(api, "monitor", manager)
    client = TestClient(api.app)
    assert client.get("/api/monitor").json()["phase"] == "idle"
    assert (
        client.post(
            "/api/monitor/start", json={"name": "Test", "occurred_at": "2020-01-01T00:00:00Z"}
        ).status_code
        == 422
    )
    assert client.post("/api/monitor/stop").json()["active"] is False
    pointer = tmp_path / "latest.json"
    assert not pointer.exists()


def test_partial_baseline_is_ingested_without_inventing_event_data(tmp_path, monkeypatch):
    from aftershocks import live_worker
    from aftershocks.monitor import atomic_json

    event_hour = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    run = tmp_path / "run"
    cache = tmp_path / "cache"
    atomic_json(
        run / "config.json",
        {"name": "Partial baseline", "occurred_at": event_hour.isoformat(), "exclude_terms": []},
    )

    class FakeSpark:
        class Conf:
            def set(self, *_):
                pass

        conf = Conf()

        def stop(self):
            pass

    monkeypatch.setattr(live_worker, "spark_session", FakeSpark)
    monkeypatch.setattr(live_worker, "available_hours", lambda _: {event_hour - timedelta(hours=3)})
    monkeypatch.setattr(live_worker, "download_hour", lambda *_: {"file": "fixture.gz", "bytes": 10})
    monkeypatch.setattr(live_worker, "ingest_hour", lambda *_: {"sourceRecords": 6})
    live_worker.run_monitor(run, cache, once=True)
    state = json.loads((run / "state.json").read_text())
    assert state["baselineReady"] == 1 and state["processedHours"] == 1
    assert state["topics"] == [] and state["timeline"] == []
    assert any("Waiting for baseline files" in row["message"] for row in state["log"])


def test_cache_lock_prevents_concurrent_writers(tmp_path):
    import fcntl

    from aftershocks.live_worker import run_monitor
    from aftershocks.monitor import atomic_json

    run = tmp_path / "run"
    cache = tmp_path / "cache"
    cache.mkdir()
    atomic_json(
        run / "config.json",
        {"name": "Lock test", "occurred_at": datetime.now(UTC).isoformat(), "exclude_terms": []},
    )
    with (cache / ".worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="Another monitor"):
            run_monitor(run, cache, once=True)
    assert json.loads((run / "state.json").read_text())["phase"] == "failed"


def test_headline_exclusion_decodes_titles_without_destroying_plus_signs(spark):
    titles = ["Encoded%27topic", "C++", "Broken%escape", "Keep_me"]
    baseline = spark.createDataFrame(
        [(title, str(i), 20) for title in titles for i in range(3)], ["article", "hour", "views"]
    )
    current = spark.createDataFrame([(title, "3", 400) for title in titles], ["article", "hour", "views"])
    rows = anomaly_candidates(baseline, current, ["encoded'topic", "c++", "broken%escape"]).collect()
    assert [r.article for r in rows] == ["Keep_me"]


def test_stop_does_not_overwrite_a_worker_owned_by_another_api(tmp_path):
    from aftershocks.monitor import atomic_json

    run = tmp_path / "runs" / "external"
    atomic_json(tmp_path / "latest.json", {"id": "external"})
    atomic_json(run / "state.json", {"phase": "processing", "message": "Other API owns this worker"})
    manager = MonitorManager(tmp_path)
    manager.stop()
    assert json.loads((run / "state.json").read_text())["phase"] == "processing"
