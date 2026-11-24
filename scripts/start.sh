#!/usr/bin/env bash
# RUN PHASE (offline): starts the stack without pulling or building anything.
source "$(dirname "$0")/common.sh"
[ -f .env ] || { fail "Falta .env: ejecute primero 'make install'"; exit 1; }
"${COMPOSE[@]}" up -d --pull never --no-build
info "Esperando a que los servicios estén sanos…"
for i in $(seq 1 90); do
  unhealthy="$("${COMPOSE[@]}" ps --format '{{.Service}} {{.Health}}' | awk '$2 != "healthy" && $2 != "" {print $1}')"
  [ -z "$unhealthy" ] && break
  sleep 2
done
"${COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}'
[ -n "${unhealthy:-}" ] && warn "Servicios aún no sanos: $unhealthy (vea: make logs)"
ok "Abra http://127.0.0.1:$(port) — la clave de acceso está en .env (VIE_ACCESS_KEY)."
