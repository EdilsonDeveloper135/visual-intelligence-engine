#!/usr/bin/env bash
# Failure-recovery tests on the running stack (stops/kills containers on purpose).
source "$(dirname "$0")/common.sh"
PASS=0; FAILS=0
result() { if [ "$1" = 0 ]; then ok "$2"; PASS=$((PASS+1)); else fail "$2"; FAILS=$((FAILS+1)); fi; }
enable_test_origin

info "1) Modelo no disponible → resultado parcial con OCR; reintento cuando vuelve"
"${COMPOSE[@]}" stop ollama >/dev/null
id="$(vt upload boleta_ok.png full | tail -1)"
st="$(vt wait "$id" partial,completed 240 | tail -1)"
vt show "$id" | tail -1
result "$([ "$st" = partial ] && echo 0 || echo 1)" "Sin Ollama la observación queda 'partial' (estado: $st) y conserva OCR + validación"
"${COMPOSE[@]}" start ollama >/dev/null
for _ in $(seq 1 60); do [ "$(docker inspect -f '{{.State.Health.Status}}' vie-ollama-1)" = healthy ] && break; sleep 2; done
vt analyze "$id" >/dev/null
st="$(vt wait "$id" completed,partial 400 | tail -1)"
result "$([ "$st" = completed ] && echo 0 || echo 1)" "Tras volver Ollama, la re-interpretación completa la observación (estado: $st)"

info "2) Worker eliminado (SIGKILL) a mitad de un job → el job se reclama al expirar el lease"
id="$(vt upload factura_ok.png full | tail -1)"
vt wait "$id" interpreting 120 >/dev/null || true
docker kill -s KILL vie-worker-1 >/dev/null
sleep 3
"${COMPOSE[@]}" up -d --no-build worker >/dev/null
st="$(vt wait "$id" completed,partial 420 | tail -1)"
result "$([ "$st" = completed ] && echo 0 || echo 1)" "Job reclamado y completado tras la caída del worker (estado: $st)"

info "3) Motor de visión caído brevemente → reintento automático con espera"
"${COMPOSE[@]}" stop vision >/dev/null
id="$(vt upload factura_rotada_7.jpg ocr_only | tail -1)"
sleep 4
"${COMPOSE[@]}" start vision >/dev/null
st="$(vt wait "$id" completed 240 | tail -1)"
result "$([ "$st" = completed ] && echo 0 || echo 1)" "La lectura se reintenta y completa cuando vuelve el motor de visión (estado: $st)"
echo
echo "Resultado: $PASS correctas, $FAILS fallas"
[ "$FAILS" -eq 0 ]
