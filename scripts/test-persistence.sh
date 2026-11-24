#!/usr/bin/env bash
# Restart the whole stack (without removing volumes) and check that data survives.
source "$(dirname "$0")/common.sh"
enable_test_origin
id="$(vt upload factura_ok.png ocr_only | tail -1)"
vt wait "$id" completed 120 >/dev/null
before="$(vt count | tail -1)"
info "Observaciones antes del reinicio: $before"
"${COMPOSE[@]}" down >/dev/null
bash scripts/start.sh >/dev/null
enable_test_origin
after="$(vt count | tail -1)"
info "Observaciones después del reinicio: $after"
vt show "$id" | tail -1
if [ "$before" = "$after" ]; then
  ok "Los datos persisten tras docker compose down + up ($after observaciones; imágenes accesibles)"
else
  fail "Se perdieron datos ($before → $after)"
  exit 1
fi
