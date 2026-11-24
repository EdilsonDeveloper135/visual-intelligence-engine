# Vision engine (vision + OCR): decodes untrusted media, preprocesses, OCR, QR/barcodes.
# Runs as uid 10001 with a read-only root filesystem and no network egress.
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

# ---- dependencies (locked) ---------------------------------------------------
FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ---- OCR models (downloaded + SHA-256 verified at BUILD time only) -----------
FROM base AS models
COPY build/fetch_models.py /build/fetch_models.py
RUN python /build/fetch_models.py /opt/models/rapidocr

# ---- runtime -------------------------------------------------------------------
FROM base AS runtime
COPY --from=deps /opt/venv /opt/venv
COPY --from=models /opt/models /opt/models
COPY vision /app/vision
RUN useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin vie \
 && python -m compileall -q /app/vision
ENV VIE_MODELS_DIR=/opt/models/rapidocr \
    OMP_NUM_THREADS=3 \
    MALLOC_ARENA_MAX=2 \
    MALLOC_TRIM_THRESHOLD_=65536 \
    HF_HUB_OFFLINE=1 \
    DO_NOT_TRACK=1
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=8).status == 200 else 1)"]
CMD ["uvicorn", "vision.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-server-header", "--no-access-log", "--timeout-keep-alive", "30"]

# ---- test target (adds dev dependencies and tests) ----------------------------
FROM runtime AS test
USER root
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY tests /app/tests
USER 10001:10001
CMD ["pytest", "-q", "-p", "no:cacheprovider"]
