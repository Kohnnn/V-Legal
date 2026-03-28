# syntax=docker/dockerfile:1

FROM python:3.12-slim

ARG VLEGAL_BOOTSTRAP_LIMIT=500

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VLEGAL_ENVIRONMENT=production \
    VLEGAL_BOOTSTRAP_LIMIT=${VLEGAL_BOOTSTRAP_LIMIT}

WORKDIR /app

RUN adduser --disabled-password --gecos "" --home "/nonexistent" --no-create-home appuser

COPY pyproject.toml uv.lock README.md ./
COPY scripts ./scripts
COPY src ./src
COPY static ./static
COPY templates ./templates

RUN python -m pip install --no-cache-dir uv \
    && mkdir -p data \
    && uv sync --frozen \
    && uv run python scripts/prepare_demo_bundle.py --limit ${VLEGAL_BOOTSTRAP_LIMIT} --seed-only-taxonomy \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "uv run uvicorn vlegal_prototype.app:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000}"]
