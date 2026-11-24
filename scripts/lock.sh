#!/usr/bin/env bash
# Regenerates dependency lockfiles INSIDE containers (nothing is installed on the host).
# INSTALL/DEVELOPMENT PHASE ONLY: needs Internet access to PyPI / npm.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY_IMAGE="python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
NODE_IMAGE="node:24.22.3-alpine3.24@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5"
UID_GID="$(id -u):$(id -g)"

lock_python() {
  local dir="$1"
  echo ">> uv lock: $dir"
  docker run --rm --user "$UID_GID" -e HOME=/tmp -e UV_CACHE_DIR=/tmp/uv-cache \
    -v "$ROOT/$dir":/app -w /app "$PY_IMAGE" \
    sh -c 'pip install -q --no-cache-dir --target /tmp/uvpkg uv==0.13.9 && /tmp/uvpkg/bin/uv lock'
}

lock_node() {
  echo ">> npm lockfile: frontend"
  docker run --rm --user "$UID_GID" -e HOME=/tmp -e npm_config_cache=/tmp/npm-cache \
    -e npm_config_fund=false -e npm_config_audit=false -e npm_config_update_notifier=false \
    -v "$ROOT/frontend":/app -w /app "$NODE_IMAGE" npm install --package-lock-only --ignore-scripts
}

targets=("$@")
[ ${#targets[@]} -eq 0 ] && targets=(tests services/vision backend frontend)
for t in "${targets[@]}"; do
  case "$t" in
    frontend) lock_node ;;
    *) lock_python "$t" ;;
  esac
done
