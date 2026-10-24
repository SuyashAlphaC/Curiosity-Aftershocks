"""Read-only local analytics API serving atomically published Spark results."""

import csv
import io
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("AFTERSHOCKS_DATA", str(ROOT / "data/processed/dashboard.json")))
app = FastAPI(title="Curiosity Aftershocks", version="1.0.0")


def dataset():
    if not DATA.exists():
        raise HTTPException(503, "No analytics available. Run: make data")
    try:
        return json.loads(DATA.read_text())
    except (OSError, ValueError):
        raise HTTPException(503, "Analytics artifact is unreadable. Rebuild with: make data") from None


@app.get("/api/health")
def health():
    return {"status": "ready" if DATA.exists() else "awaiting_data", "version": "1.0.0"}


@app.get("/api/events")
def events():
    return [
        {k: v for k, v in e.items() if k not in ("topics", "edges", "timeline")} for e in dataset()["events"]
    ]


@app.get("/api/events/{event_id}")
def event(event_id: str):
    for item in dataset()["events"]:
        if item["id"] == event_id:
            return item
    raise HTTPException(404, "Unknown event")


@app.get("/api/pipeline")
def pipeline():
    result = dataset()["pipeline"]
    bulk = DATA.parent / "bulk-report.json"
    if bulk.exists():
        result["bulk"] = json.loads(bulk.read_text())
    return result


@app.get("/api/events/{event_id}/export")
def export(event_id: str):
    item = event(event_id)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["article", "category", "date", "day", "views", "baseline", "lift", "z", "cluster"])
    for topic in item["topics"]:
        for point in topic["series"]:
            # Neutralize spreadsheet formula prefixes in text columns.
            title = topic["title"]
            if title.startswith(("=", "+", "-", "@")):
                title = "'" + title
            writer.writerow(
                [
                    title,
                    topic["category"],
                    point["date"],
                    point["day"],
                    point["views"],
                    topic["baseline"],
                    point["lift"],
                    point["z"],
                    topic["cluster"],
                ]
            )
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="aftershocks-{event_id}.csv"'},
    )


DIST = ROOT / "frontend/dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(DIST / "favicon.svg")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(DIST / "index.html")
