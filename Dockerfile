# syntax=docker/dockerfile:1

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VLEGAL_ENVIRONMENT=production

WORKDIR /app

RUN adduser --disabled-password --gecos "" --home "/nonexistent" --no-create-home appuser

COPY pyproject.toml uv.lock README.md ./
COPY scripts ./scripts
COPY src ./src
COPY static ./static
COPY templates ./templates

RUN python -m pip install --no-cache-dir uv \
    && uv sync --frozen \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "uv run uvicorn vlegal_prototype.app:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
