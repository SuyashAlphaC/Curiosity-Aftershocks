import json
import math

import pytest
from fastapi.testclient import TestClient

from aftershocks import api
from aftershocks.bulk import parse_dump
from aftershocks.pipeline import lagged_edges, score_observations, spark_session


@pytest.fixture(scope="module")
def spark():
    session = spark_session("local[2]")
    yield session
    session.stop()


def test_baseline_excludes_event_and_handles_zero_variance(spark):
    frame = spark.createDataFrame(
        [
            ("x", "A", "2024-01-01", 10),
            ("x", "A", "2024-01-02", 10),
            ("x", "A", "2024-01-03", 100),
            ("x", "B", "2024-01-01", 0),
            ("x", "B", "2024-01-02", 0),
            ("x", "B", "2024-01-03", 5),
        ],
        ["event_id", "article", "date", "views"],
    )
    dates = spark.createDataFrame([("x", "2024-01-03")], ["event_id", "event_date"])
    rows = {r.article: r for r in score_observations(frame, dates).filter("day=0").collect()}
    assert rows["A"].baseline == 10
    assert rows["A"].lift == 10
    assert rows["A"].excess == 90
    assert rows["A"].z == pytest.approx(90 / math.sqrt(10))
    assert rows["B"].lift == 5
    assert rows["B"].z == 5


def test_dump_parser_rejects_bad_rows_and_preserves_encoded_titles(spark):
    lines = spark.createDataFrame(
        [
            (v,)
            for v in [
                "en Moon 123 0",
                "en.m Solar_eclipse 42 0",
                "en Bad not-a-number 0",
                "en Negative -3 0",
                "broken",
                "en Too_many 3 0 extra",
                "en Baily%27s_beads 7 0",
            ]
        ],
        ["value"],
    )
    rows = parse_dump(lines).collect()
    assert [r.article for r in rows if r.valid] == ["Moon", "Solar_eclipse", "Baily%27s_beads"]
    assert sum(bool(r.valid) for r in rows) == 3


def test_lag_detection_and_constant_series():
    signal = [3, 5, 4, 20, 80, 30, 10, 4, 5, 9, 7, 3, 6, 4, 5, 7, 3, 8, 4, 6, 2, 3]

    def topic(name, values):
        return {
            "id": name,
            "category": "Science",
            "series": [{"day": i, "views": v} for i, v in enumerate(values)],
        }

    edges = lagged_edges([topic("A", signal), topic("B", [1, 2] + signal[:-2]), topic("flat", [10] * 22)])
    assert len(edges) == 1
    assert edges[0]["source"] == "A"
    assert edges[0]["target"] == "B"
    assert edges[0]["lag"] == 2
    assert edges[0]["correlation"] == pytest.approx(1)


def test_api_missing_data_unknown_event_and_export(tmp_path, monkeypatch):
    path = tmp_path / "dashboard.json"
    monkeypatch.setattr(api, "DATA", path)
    client = TestClient(api.app)
    assert client.get("/api/health").json()["status"] == "awaiting_data"
    assert client.get("/api/events").status_code == 503
    path.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "id": "test",
                        "topics": [
                            {
                                "title": "=formula",
                                "category": "Control",
                                "baseline": 2,
                                "cluster": 0,
                                "series": [{"date": "2024-01-01", "day": 0, "views": 4, "lift": 2, "z": 1}],
                            }
                        ],
                    }
                ]
            }
        )
    )
    assert client.get("/api/events/missing").status_code == 404
    response = client.get("/api/events/test/export")
    assert response.status_code == 200
    assert "'=formula" in response.text
    assert "text/csv" in response.headers["content-type"]
    assert client.get("/api/events").json() == [{"id": "test"}]


def test_real_artifact_integrity():
    path = api.ROOT / "data/processed/dashboard.json"
    if not path.exists():
        pytest.skip("Run make data for real-artifact integration checks")
    payload = json.loads(path.read_text())
    assert len(payload["events"]) == 3
    assert payload["pipeline"]["records"] == 2850
    for event in payload["events"]:
        assert len(event["topics"]) == 19
        assert len(event["timeline"]) == 50
        assert event["stats"]["totalViews"] == sum(t["totalViews"] for t in event["topics"])
        for topic in event["topics"]:
            assert len(topic["series"]) == 50
            baseline = sum(p["views"] for p in topic["series"] if p["day"] < 0) / 28
            assert topic["baseline"] == pytest.approx(baseline, abs=0.01)
            assert topic["totalViews"] == sum(p["views"] for p in topic["series"] if p["day"] >= 0)
            assert math.isfinite(topic["peakZ"])


def test_rate_limit_backoff_respects_upstream():
    from aftershocks.ingest import retry_delay

    assert retry_delay("HTTP/2 429\r\nRetry-After: 600\r\n", 0) == 600
    assert retry_delay("retry-after: 3\n", 1) == 240
    assert retry_delay("Retry-After: malformed\n", 0) == 120


def test_incomplete_cached_series_is_not_imputed(tmp_path):
    import hashlib

    from aftershocks.ingest import API, fetch_topic

    event = {"id": "example", "date": "2024-04-08", "topics": {"Moon": "Astronomy"}}
    url = f"{API}/en.wikipedia/all-access/user/Moon/daily/2024031100/2024042900"
    key = hashlib.sha256(url.encode()).hexdigest()[:20]
    (tmp_path / "responses").mkdir()
    (tmp_path / "responses" / f"{key}.json").write_text(
        json.dumps({"items": [{"timestamp": "2024040800", "views": 50}]})
    )
    with pytest.raises(ValueError, match="Incomplete series"):
        fetch_topic(event, "Moon", tmp_path)
