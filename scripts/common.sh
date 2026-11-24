#!/usr/bin/env bash
# Shared helpers for the operation scripts.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f docker-compose.yml)
info() { printf '\033[1;34m>>\033[0m %s\n' "$*"; }
ok() { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*"; }
env_value() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2-; }
port() { local p; p="$(env_value VIE_PORT)"; echo "${p:-8765}"; }
TEST_COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test)
# Runs the test CLI (tests/system/tools.py) inside the frontend's network namespace.
vt() { "${TEST_COMPOSE[@]}" run --rm --no-deps -T system-tests python -m system.tools "$@"; }
enable_test_origin() { docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --no-build api >/dev/null 2>&1; sleep 4; }
