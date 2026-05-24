# syntax=docker/dockerfile:1.7
# AlecaFrame backend / poller image.
# Same image, two entrypoints — chosen via `command:` in docker-compose.

FROM python:3.13-slim AS builder

# uv via the official image (cached layer)
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON=python3.13 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Install deps first (cache-friendly layer)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Now copy source and install the project itself
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.13-slim AS runtime

RUN useradd -m -u 1000 aleca \
    && mkdir -p /data \
    && chown aleca:aleca /data

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ALECA_HOST=0.0.0.0

WORKDIR /app
COPY --from=builder --chown=aleca:aleca /app/.venv /app/.venv
COPY --from=builder --chown=aleca:aleca /app/src /app/src

USER aleca
EXPOSE 8765

# Default to the API; the poller service overrides this in compose.
CMD ["alecaframe-api"]
