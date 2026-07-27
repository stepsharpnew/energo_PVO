# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.9.25 AS uv

FROM python:3.12-slim-bookworm

ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PATH="/app/.venv/bin:${PATH}"

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        fonts-crosextra-caladea \
        fonts-crosextra-carlito \
        fonts-dejavu-core \
        fonts-liberation2 \
        libreoffice-calc \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY agent-skill ./agent-skill
COPY profiles ./profiles
COPY template ./template
COPY templates ./templates
COPY scripts/clean_pilot_templates.py ./scripts/clean_pilot_templates.py

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
RUN uv run python scripts/clean_pilot_templates.py > /dev/null \
    && mkdir -p /app/bundled-approved \
    && cp /app/templates/approved/*.xlsx /app/bundled-approved/

EXPOSE 8000

CMD ["uvicorn", "--app-dir", "src", "executive_docs.main:app", "--host", "0.0.0.0", "--port", "8000"]
