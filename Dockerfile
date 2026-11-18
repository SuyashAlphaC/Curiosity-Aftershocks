FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY aftershocks ./aftershocks
COPY deploy/data ./data/processed
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    SPARK_LOCAL_IP=127.0.0.1 \
    AFTERSHOCKS_MONITOR_DIR=/data/monitor
CMD ["sh", "-c", "exec uvicorn aftershocks.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
