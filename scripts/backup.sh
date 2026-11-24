#!/usr/bin/env bash
# Backup: database (pg_dump custom format) + files volume (originals and derived copies).
# Models are re-downloadable and excluded unless --with-models. Secrets (.env) are NOT included.
source "$(dirname "$0")/common.sh"
WITH_MODELS=0; [ "${1:-}" = "--with-models" ] && WITH_MODELS=1
ts="$(date +%Y%m%d-%H%M%S)"
dest="$ROOT/data/backups/vie-$ts"
mkdir -p "$dest"
info "Base de datos → $dest/db.dump"
"${COMPOSE[@]}" exec -T postgres pg_dump -U vie -d vie -Fc > "$dest/db.dump"
info "Archivos (vie_files) → $dest/files.tar.gz"
docker run --rm --user 10001:10001 -v vie_files:/data:ro -v "$dest":/backup --entrypoint tar vie/backend:1.0.0 \
  czf /backup/files.tar.gz -C /data originals derived
if [ $WITH_MODELS -eq 1 ]; then
  info "Modelos (vie_ollama) → $dest/models.tar"
  docker run --rm --user 10001:10001 -v vie_ollama:/m:ro -v "$dest":/backup --entrypoint tar vie/backend:1.0.0 cf /backup/models.tar -C /m .
fi
( cd "$dest" && shasum -a 256 ./* > SHA256SUMS )
cat > "$dest/manifest.json" <<JSON
{"created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)", "app_version": "1.0.0", "db_format": "pg_dump custom",
 "includes_models": $([ $WITH_MODELS -eq 1 ] && echo true || echo false), "secrets_included": false}
JSON
ok "Respaldo creado en $dest ($(du -sh "$dest" | cut -f1)). Guarde también su archivo .env en un lugar seguro."
