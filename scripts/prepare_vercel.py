"""Package the frontend with an explicit, healthy persistent API upstream."""

import argparse
import json
import shutil
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def prepare(backend):
    backend = backend.rstrip("/")
    parsed = urlsplit(backend)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Supply the backend HTTPS origin, without a path or query")
    with urllib.request.urlopen(backend + "/api/health", timeout=30) as response:
        if json.load(response).get("status") != "ready":
            raise RuntimeError("Backend analytics are not ready")
    with urllib.request.urlopen(backend + "/api/monitor", timeout=30) as response:
        if not isinstance(json.load(response).get("active"), bool):
            raise RuntimeError("Backend monitor endpoint is unavailable")
    source = ROOT / "frontend/dist"
    if not (source / "index.html").exists():
        raise RuntimeError("Build the frontend first: npm --prefix frontend run build")
    target = ROOT / "deploy/vercel"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    (target / "vercel.json").write_text(
        json.dumps(
            {
                "$schema": "https://openapi.vercel.sh/vercel.json",
                "framework": None,
                "rewrites": [{"source": "/api/:path*", "destination": backend + "/api/:path*"}],
                "headers": [
                    {"source": "/api/:path*", "headers": [{"key": "Cache-Control", "value": "no-store"}]}
                ],
            },
            indent=2,
        ) + "\n"
    )
    print(f"Prepared {target} with verified backend {backend}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend", help="Public HTTPS origin for the persistent backend")
    prepare(parser.parse_args().backend)
