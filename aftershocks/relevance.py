"""Conservative event relevance: public article text + Spark MLlib TF-IDF."""

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from urllib.parse import unquote, urlencode

from pyspark.ml.feature import IDF, HashingTF, Normalizer, StopWordsRemover
from pyspark.ml.linalg import SparseVector, VectorUDT
from pyspark.sql import functions as F

from aftershocks.ingest import USER_AGENT
from aftershocks.monitor import atomic_json

THRESHOLD = 0.06
MAX_CANDIDATES = 300
STOP = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "in",
    "on",
    "at",
    "to",
    "from",
    "for",
    "with",
    "by",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "their",
    "they",
    "we",
    "our",
    "about",
    "after",
    "before",
    "during",
    "over",
    "under",
    "into",
    "currently",
    "ongoing",
} | {
    "event",
    "recent",
    "monitoring",
    "window",
    "monitor",
    "news",
    "coverage",
    "current",
}
ALIASES = {
    "france": {"france", "french"},
    "protest": {
        "protest",
        "protests",
        "protester",
        "protesters",
        "demonstration",
        "demonstrations",
        "unrest",
        "riot",
        "riots",
        "uprising",
        "strike",
        "strikes",
    },
}


def words(text):
    return [w for w in re.findall(r"[^\W\d_]+", text.lower()) if len(w) > 2 and w not in STOP]


def canonical(word):
    for key, variants in ALIASES.items():
        if word in variants:
            return key
    return word


def anchors(config):
    terms = config.get("relevance_terms") or words(config["name"])
    return list(dict.fromkeys(canonical(w) for term in terms for w in words(term)))[:8]


def fetch_documents(titles, cache):
    """Batched lead text/categories, 24h cache; never substitute invented content."""
    cache.mkdir(parents=True, exist_ok=True)
    result, pending = {}, []
    for title in titles:
        path = cache / (hashlib.sha256(title.encode()).hexdigest() + ".json")
        if path.exists() and datetime.now().timestamp() - path.stat().st_mtime < 86400:
            result[title] = json.loads(path.read_text())
        else:
            pending.append(title)
    for start in range(0, len(pending), 20):
        batch = pending[start : start + 20]
        params = {
            "action": "query",
            "format": "json",
            "formatversion": 2,
            "prop": "extracts|categories",
            "exintro": 1,
            "explaintext": 1,
            "exlimit": 20,
            "cllimit": 20,
            "redirects": 1,
            "titles": "|".join(unquote(t).replace("_", " ") for t in batch),
        }
        url = "https://en.wikipedia.org/w/api.php?" + urlencode(params)
        response = subprocess.run(
            [
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--max-time",
                "45",
                "--user-agent",
                USER_AGENT,
                url,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(response.stdout)
        if "error" in data or "query" not in data:
            raise ValueError("Wikipedia article descriptions are unavailable")
        query = data["query"]
        redirects = {x["from"]: x["to"] for x in query.get("normalized", []) + query.get("redirects", [])}
        pages = {p["title"]: p for p in query.get("pages", [])}
        for title in batch:
            resolved = unquote(title).replace("_", " ")
            for _ in range(10):
                if resolved not in redirects:
                    break
                resolved = redirects[resolved]
            page = pages.get(resolved, {})
            doc = {
                "title": resolved,
                "summary": page.get("extract", "")[:6000],
                "categories": [c["title"].removeprefix("Category:") for c in page.get("categories", [])],
                "url": "https://en.wikipedia.org/?curid=" + str(page.get("pageid", "")),
                "retrievedAt": datetime.now(UTC).isoformat(),
            }
            result[title] = doc
            # Missing/empty descriptions are excluded and retried on the next scan.
            if doc["summary"]:
                atomic_json(cache / (hashlib.sha256(title.encode()).hexdigest() + ".json"), doc)
    return result


def rank_relevance(spark, documents, config):
    """All anchor concepts AND cosine threshold must pass. Score is not confidence."""
    required = anchors(config)
    if len(required) < 2:
        raise ValueError("Add at least two specific event terms (for example: France, protest).")
    context = config["name"] + " " + config.get("event_context", "") + " " + " ".join(required)
    query_words = [canonical(w) for w in words(context)]
    valid = {k: d for k, d in documents.items() if d.get("summary")}
    if not valid:
        return {}
    tokens = {
        key: [
            canonical(w)
            for w in words(doc["title"] + " " + doc["summary"] + " " + " ".join(doc["categories"]))
        ]
        for key, doc in valid.items()
    }
    frame = spark.createDataFrame([("__event__", query_words)] + list(tokens.items()), ["id", "words"])
    frame = StopWordsRemover(inputCol="words", outputCol="clean").transform(frame)
    tf = HashingTF(inputCol="clean", outputCol="tf", numFeatures=262144, binary=True).transform(frame)
    model = IDF(inputCol="tf", outputCol="weighted").fit(tf)

    # Add one to IDF weights so shared words survive in very small candidate pools.
    @F.udf(VectorUDT())
    def smooth(raw, weighted):
        values = dict(zip(weighted.indices.tolist(), weighted.values.tolist()))
        return SparseVector(
            raw.size, {int(i): float(v) + values.get(int(i), 0.0) for i, v in zip(raw.indices, raw.values)}
        )

    weighted = model.transform(tf).withColumn("smoothed", smooth("tf", "weighted"))
    normalized = Normalizer(inputCol="smoothed", outputCol="vector").transform(weighted)
    vectors = {r.id: r.vector for r in normalized.select("id", "vector").collect()}
    query = vectors.pop("__event__")
    accepted = {}
    for key, vector in vectors.items():
        matches = sorted(set(required) & set(tokens[key]))
        score = float(query.dot(vector))
        if len(matches) == len(required) and score >= THRESHOLD:
            doc = valid[key]
            accepted[key] = {
                "score": round(score, 4),
                "matchedTerms": matches,
                "reason": "Article text/categories match every required event concept: " + ", ".join(matches),
                "summary": doc["summary"][:800],
                "sourceUrl": doc["url"],
                "retrievedAt": doc["retrievedAt"],
                "method": "Spark MLlib TF-IDF cosine similarity",
            }
    return accepted


def filter_candidates(spark, candidates, config, cache):
    documents = fetch_documents([r.article for r in candidates], cache)
    accepted = rank_relevance(spark, documents, config)
    return (
        [r for r in candidates if r.article in accepted][:24],
        accepted,
        {
            "method": "Spark MLlib HashingTF + IDF + cosine; all required concepts",
            "threshold": THRESHOLD,
            "requiredTerms": anchors(config),
            "checked": len(candidates),
            "withText": sum(bool(d.get("summary")) for d in documents.values()),
            "accepted": len(accepted),
            "poolLimit": MAX_CANDIDATES,
        },
    )
