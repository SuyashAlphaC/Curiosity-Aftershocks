from datetime import UTC, datetime

import pytest

from aftershocks.pipeline import spark_session
from aftershocks.relevance import anchors, fetch_documents, rank_relevance


@pytest.fixture(scope="module")
def spark():
    session = spark_session("local[2]")
    yield session
    session.stop()


def doc(title, summary):
    return {
        "title": title,
        "summary": summary,
        "categories": [],
        "url": "https://en.wikipedia.org/wiki/Test",
        "retrievedAt": datetime.now(UTC).isoformat(),
    }


def test_relevance_rejects_sports_films_and_wrong_country(spark):
    docs = {
        "related": doc(
            "French demonstrations", "French protesters organized demonstrations and strikes in France."
        ),
        "actor": doc("Olivia Newton-John", "British Australian singer and actress starring in Grease film."),
        "sport": doc("Football in France", "French football players and sports stadiums in France."),
        "elsewhere": doc(
            "Protests in Canada", "Canadian protesters organized demonstrations and strikes in Canada."
        ),
        "missing": doc("France protest", ""),
    }
    result = rank_relevance(spark, docs, {"name": "France protest"})
    assert set(result) == {"related"}
    assert result["related"]["matchedTerms"] == ["france", "protest"]
    assert 0.12 <= result["related"]["score"] <= 1


def test_single_relevant_document_and_context(spark):
    result = rank_relevance(
        spark, {"one": doc("France protest", "France protest")}, {"name": "France protest"}
    )
    assert result["one"]["score"] == pytest.approx(1)
    assert rank_relevance(spark, {}, {"name": "France protest"}) == {}
    with pytest.raises(ValueError, match="two specific"):
        rank_relevance(spark, {}, {"name": "News"})
    assert anchors({"name": "My demo", "relevance_terms": ["French", "protests"]}) == ["france", "protest"]


def test_failed_metadata_never_falls_back_to_titles(tmp_path, monkeypatch):
    import subprocess

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(22, "curl")

    monkeypatch.setattr("aftershocks.relevance.subprocess.run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        fetch_documents(["France_protest"], tmp_path)
    assert list(tmp_path.glob("*.json")) == []


def test_discovery_filters_before_top24_selection(spark, tmp_path, monkeypatch):
    from datetime import timedelta

    from aftershocks.live_worker import discovery_snapshot, hour_key

    event = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    baseline = [event - timedelta(hours=i) for i in (3, 2, 1)]
    names = [f"Sports_{i}" for i in range(25)] + ["French_protest"]
    for hour in baseline + [event]:
        rows = [
            (name, hour_key(hour), 20 if hour < event else (400 if name == "French_protest" else 1000))
            for name in names
        ]
        spark.createDataFrame(rows, ["article", "hour", "views"]).write.parquet(
            str(tmp_path / hour_key(hour) / "parquet")
        )
    documents = {name: doc(name, "French football stadium sports in France") for name in names}
    documents["French_protest"] = doc("French protest", "Protests and demonstrations in France")
    monkeypatch.setattr("aftershocks.relevance.fetch_documents", lambda *_: documents)
    result = discovery_snapshot(spark, tmp_path, baseline, [event], [], {"name": "France protest"})
    assert result["candidateCount"] == 26
    assert result["relevance"]["checked"] == 26
    assert [t["id"] for t in result["topics"]] == ["French_protest"]
    assert result["relatedCount"] == 1
    assert result["edges"] == []
