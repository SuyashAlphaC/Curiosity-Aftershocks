"""Local analytics API and explicit start/stop lifecycle for the recent-event monitor."""

import asyncio
import csv
import io
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from aftershocks.monitor import MonitorConfig, MonitorManager

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("AFTERSHOCKS_DATA", str(ROOT / "data/processed/dashboard.json")))
monitor = MonitorManager(os.environ.get("AFTERSHOCKS_MONITOR_DIR", str(ROOT / "data/monitor")))


@asynccontextmanager
async def lifespan(_app):
    yield
    if monitor.process is not None:
        await asyncio.to_thread(monitor.stop)


app = FastAPI(title="Curiosity Aftershocks", version="1.1.0", lifespan=lifespan)


@app.get("/api/monitor")
def monitor_status():
    return monitor.status()


@app.post("/api/monitor/start")
def start_monitor(config: MonitorConfig):
    from aftershocks.relevance import anchors

    if len(anchors(config.model_dump())) < 2:
        raise HTTPException(422, "Provide at least two specific event concepts, such as France, protest.")
    try:
        return monitor.start(config)
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from error


@app.post("/api/monitor/stop")
def stop_monitor():
    return monitor.stop()


def dataset():
    if not DATA.exists():
        raise HTTPException(503, "No analytics available. Run: make data")
    try:
        return json.loads(DATA.read_text())
    except (OSError, ValueError):
        raise HTTPException(503, "Analytics artifact is unreadable. Rebuild with: make data") from None


@app.get("/api/health")
def health():
    return {"status": "ready" if DATA.exists() else "awaiting_data", "version": app.version}


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
