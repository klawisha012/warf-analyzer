# syntax=docker/dockerfile:1.7
# Poller image — identical recipe to backend, different entrypoint.
# We re-derive from python:3.13-slim instead of FROM backend to keep this
# file self-contained (docker-compose can build either in any order).

FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON=python3.13 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY backend/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.13-slim AS runtime

RUN useradd -m -u 1000 aleca \
    && mkdir -p /data \
    && chown aleca:aleca /data

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    # uv pre-compiled .pyc at build time (UV_COMPILE_BYTECODE=1);
    # this flag tells the interpreter never to scatter .pyc for any un-compiled module.
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --from=builder --chown=aleca:aleca /app/.venv /app/.venv
COPY --from=builder --chown=aleca:aleca /app/src /app/src

USER aleca

CMD ["alecaframe-poller"]
