#!/usr/bin/env bash
# Proves that the runtime has no Internet access and still works end to end.
source "$(dirname "$0")/common.sh"
PASS=0; FAILS=0
expect_blocked() {  # container, description, command...
  local c="$1" desc="$2"; shift 2
  if docker exec "$c" "$@" >/dev/null 2>&1; then fail "$c: $desc ALCANZABLE"; FAILS=$((FAILS+1)); else ok "$c: $desc bloqueado"; PASS=$((PASS+1)); fi
}
PY_TCP='import socket,sys; s=socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=4)'
PY_DNS='import socket; socket.getaddrinfo("example.com", 443)'
for c in vie-api-1 vie-worker-1 vie-vision-1; do
  expect_blocked "$c" "TCP a 1.1.1.1:443" python -c "$PY_TCP" 1.1.1.1 443
  expect_blocked "$c" "TCP a 8.8.8.8:53" python -c "$PY_TCP" 8.8.8.8 53
  expect_blocked "$c" "DNS externo (example.com)" python -c "$PY_DNS"
  expect_blocked "$c" "host.docker.internal:8080 (otros servicios del equipo)" python -c "$PY_TCP" host.docker.internal 8080
done
expect_blocked vie-ollama-1 "TCP a 1.1.1.1:443" bash -c 'exec 3<>/dev/tcp/1.1.1.1/443'
expect_blocked vie-ollama-1 "registry.ollama.ai" bash -c 'exec 3<>/dev/tcp/registry.ollama.ai/443'
expect_blocked vie-postgres-1 "TCP a 1.1.1.1:80" wget -q -T 4 -O /dev/null http://1.1.1.1
warn "frontend (nginx) está en la red 'edge', necesaria para publicar 127.0.0.1:$(port); no inicia conexiones salientes ni guarda datos."

info "Prueba funcional sin Internet: carga + OCR + modelo + validación"
enable_test_origin
id="$(vt upload factura_ok.png full | tail -1)"
st="$(vt wait "$id" completed,partial 400 | tail -1)"
vt show "$id" | tail -1
if [ "$st" = completed ]; then ok "Pipeline completo funcionando sin acceso a Internet"; PASS=$((PASS+1)); else fail "Pipeline terminó en estado $st"; FAILS=$((FAILS+1)); fi
echo
echo "Resultado: $PASS correctas, $FAILS fallas"
[ "$FAILS" -eq 0 ]
