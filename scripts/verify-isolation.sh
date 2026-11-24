#!/usr/bin/env bash
# Verifies container hardening and network isolation of the running stack.
source "$(dirname "$0")/common.sh"
PASS=0; FAILS=0
check() { if [ "$2" = "true" ]; then ok "$1"; PASS=$((PASS+1)); else fail "$1"; FAILS=$((FAILS+1)); fi; }

for c in $("${COMPOSE[@]}" ps -q); do
  name="$(docker inspect -f '{{.Name}}' "$c" | sed 's#^/##')"
  priv="$(docker inspect -f '{{.HostConfig.Privileged}}' "$c")"
  caps="$(docker inspect -f '{{json .HostConfig.CapDrop}}' "$c")"
  capadd="$(docker inspect -f '{{json .HostConfig.CapAdd}}' "$c")"
  nnp="$(docker inspect -f '{{json .HostConfig.SecurityOpt}}' "$c")"
  ro="$(docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' "$c")"
  user="$(docker inspect -f '{{.Config.User}}' "$c")"
  mem="$(docker inspect -f '{{.HostConfig.Memory}}' "$c")"
  pids="$(docker inspect -f '{{.HostConfig.PidsLimit}}' "$c")"
  sock="$(docker inspect -f '{{range .Mounts}}{{.Source}} {{end}}' "$c" | grep -c docker.sock || true)"
  ports="$(docker inspect -f '{{range $p, $b := .NetworkSettings.Ports}}{{range $b}}{{.HostIp}}:{{.HostPort}} {{end}}{{end}}' "$c")"
  echo "── $name"
  check "  no privilegiado" "$([ "$priv" = false ] && echo true || echo false)"
  check "  capacidades: ALL eliminadas, ninguna añadida" "$([[ "$caps" == *ALL* ]] && [[ "$capadd" == "null" || "$capadd" == "[]" ]] && echo true || echo false)"
  check "  no-new-privileges" "$([[ "$nnp" == *no-new-privileges* ]] && echo true || echo false)"
  check "  sistema de archivos raíz de solo lectura" "$([ "$ro" = true ] && echo true || echo false)"
  check "  usuario sin privilegios ($user)" "$([ -n "$user" ] && [ "$user" != "0" ] && [ "$user" != "root" ] && echo true || echo false)"
  check "  límite de memoria ($((mem / 1048576)) MiB) y de procesos ($pids)" "$([ "$mem" -gt 0 ] && [ "$pids" -gt 0 ] && echo true || echo false)"
  check "  sin socket de Docker montado" "$([ "$sock" = 0 ] && echo true || echo false)"
  if [ -n "$ports" ]; then
    check "  puertos publicados solo en 127.0.0.1 ($ports)" "$(echo "$ports" | grep -qv '127.0.0.1' && echo false || echo true)"
  fi
done
echo "── redes"
for n in vie_app vie_core vie_ml; do
  check "  $n es interna (sin salida a Internet)" "$(docker network inspect -f '{{.Internal}}' "$n")"
done
check "  vision no alcanza la base de datos (no comparte red con postgres)" \
  "$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' vie-vision-1 | grep -q vie_core && echo false || echo true)"
check "  ollama no alcanza la base de datos" \
  "$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' vie-ollama-1 | grep -q vie_core && echo false || echo true)"
echo
echo "Resultado: $PASS correctas, $FAILS fallas"
[ "$FAILS" -eq 0 ]
