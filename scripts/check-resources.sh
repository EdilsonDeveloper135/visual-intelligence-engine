#!/usr/bin/env bash
# Checks Docker, the Docker VM memory and the free disk space before installing.
source "$(dirname "$0")/common.sh"
command -v docker >/dev/null || { fail "Docker no está instalado"; exit 1; }
docker info >/dev/null 2>&1 || { fail "El demonio de Docker no responde (¿Docker Desktop iniciado?)"; exit 1; }
docker compose version >/dev/null 2>&1 || { fail "Falta Docker Compose v2"; exit 1; }
ok "Docker $(docker version --format '{{.Server.Version}}') · Compose $(docker compose version --short)"
arch="$(docker info --format '{{.Architecture}}')"; ok "Arquitectura de contenedores: $arch"
total_kb="$(docker run --rm --entrypoint sh postgres:18.7-alpine3.24 -c 'grep MemTotal /proc/meminfo' 2>/dev/null | awk '{print $2}' || echo 0)"
avail_kb="$(docker run --rm --entrypoint sh postgres:18.7-alpine3.24 -c 'grep MemAvailable /proc/meminfo' 2>/dev/null | awk '{print $2}' || echo 0)"
if [ "${total_kb:-0}" -gt 0 ]; then
  ok "RAM de la VM de Docker: $((total_kb / 1024)) MiB (disponible ahora: $((avail_kb / 1024)) MiB)"
  [ "$((avail_kb / 1024))" -lt 5000 ] && warn "Menos de ~5 GB libres en la VM: el perfil lite necesita ~4,9 GB de límite (cierre otros stacks o aumente la RAM de Docker Desktop)."
fi
free_gb="$(df -g "$ROOT" | awk 'NR==2 {print $4}')"
[ "${free_gb:-0}" -lt 15 ] && warn "Solo ${free_gb} GB libres en disco; la instalación necesita ~12 GB." || ok "Disco libre: ${free_gb} GB"
if command -v nvidia-smi >/dev/null 2>&1; then ok "GPU NVIDIA detectada (ver docker-compose.gpu.yml)"; else ok "Sin GPU NVIDIA: inferencia en CPU (perfil lite)"; fi
