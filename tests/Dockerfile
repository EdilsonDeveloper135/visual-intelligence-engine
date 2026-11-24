# Test/tooling image: synthetic data generation + system tests (runs only in the test profile).
FROM python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /work/tests
COPY tests/pyproject.toml tests/uv.lock ./
RUN uv sync --frozen --no-dev
COPY tests/ /work/tests/
RUN useradd --uid 10001 --create-home tester
USER 10001
CMD ["python", "-m", "synthetic.generate", "--out", "/work/examples/generated", "--pdf"]
