#!/usr/bin/env bash
# Restore a backup made by backup.sh.
#  * Asks for explicit confirmation (type RESTAURAR) unless --yes is given.
#  * Makes a safety backup of the current state first.
#  * The database is replaced with the backup (pg_restore --clean).
#  * Files are extracted OVER the current volume: nothing is deleted. Files of
#    observations that do not exist in the restored database simply remain unused.
source "$(dirname "$0")/common.sh"
src="${1:-}"
if [ -z "$src" ] || [ ! -f "$src/db.dump" ] || [ ! -f "$src/files.tar.gz" ]; then
  fail "Uso: scripts/restore.sh data/backups/vie-AAAAMMDD-HHMMSS [--yes]"
  exit 1
fi
( cd "$src" && shasum -a 256 -c SHA256SUMS >/dev/null ) || { fail "El respaldo no supera la verificación SHA-256"; exit 1; }
if [ "${2:-}" != "--yes" ]; then
  warn "Esto REEMPLAZA la base de datos actual por la del respaldo $src."
  read -r -p "Escriba RESTAURAR para continuar: " answer
  [ "$answer" = "RESTAURAR" ] || { info "Cancelado."; exit 1; }
fi
info "Respaldo de seguridad del estado actual"
bash scripts/backup.sh
info "Deteniendo frontend, api y worker"
"${COMPOSE[@]}" stop frontend api worker
info "Restaurando base de datos"
"${COMPOSE[@]}" exec -T postgres pg_restore -U vie -d vie --clean --if-exists --no-owner < "$src/db.dump"
info "Restaurando archivos (extracción sobre el volumen, sin borrar)"
abs_src="$(cd "$src" && pwd)"
docker run --rm --user 10001:10001 -v vie_files:/data -v "$abs_src":/backup:ro --entrypoint tar vie/backend:1.0.0 \
  xzf /backup/files.tar.gz -C /data
"${COMPOSE[@]}" up -d --no-build --pull never api worker frontend
ok "Restauración completada."
