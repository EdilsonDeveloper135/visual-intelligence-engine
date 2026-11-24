# API + worker image (same code, different command). Build context: repository root.
ARG PYTHON_IMAGE=python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app

FROM base AS deps
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM base AS runtime
COPY --from=deps /opt/venv /opt/venv
COPY backend/alembic.ini /app/alembic.ini
COPY backend/vie /app/vie
COPY configs /app/configs
RUN useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin vie \
 && python -m compileall -q /app/vie \
 && mkdir -p /data/staging /data/originals /data/derived /data/exports \
 && touch /data/staging/.keep \
 && chown -R 10001:10001 /data
ENV VIE_CONFIGS_DIR=/app/configs \
    MALLOC_ARENA_MAX=2 \
    DO_NOT_TRACK=1 \
    TMPDIR=/data/staging
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=8s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=6).status == 200 else 1)"]
CMD ["uvicorn", "vie.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header", "--ws-max-size", "2097152", "--timeout-keep-alive", "30"]

FROM runtime AS test
USER root
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project
COPY backend/tests /app/tests
ENV TMPDIR=/tmp
USER 10001:10001
CMD ["pytest", "-q", "-p", "no:cacheprovider"]
