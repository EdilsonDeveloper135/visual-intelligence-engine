#!/usr/bin/env bash
# Creates .env from .env.example, replacing every __GENERATE__ with a random
# secret. Never overwrites an existing .env.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$ROOT/.env" ]; then
  echo ".env already exists — left untouched."
  exit 0
fi
gen() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "${1:-40}"; }
tmp="$(mktemp)"
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    VIE_ACCESS_KEY=__GENERATE__) echo "VIE_ACCESS_KEY=$(gen 24)" ;;
    *=__GENERATE__) echo "${line%%=*}=$(gen 48)" ;;
    *) echo "$line" ;;
  esac
done <"$ROOT/.env.example" >"$tmp"
mv "$tmp" "$ROOT/.env"
chmod 600 "$ROOT/.env"
echo ".env created with random secrets (permissions 600)."
