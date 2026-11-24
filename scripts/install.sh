#!/usr/bin/env bash
# =============================================================================
# INSTALL PHASE (requires Internet, run once): build images, download models,
# generate synthetic samples. After this the system runs fully offline.
# =============================================================================
source "$(dirname "$0")/common.sh"
info "Comprobando el entorno"
bash scripts/check-resources.sh
info "Configuración (.env)"
bash scripts/init-env.sh
info "Construyendo imágenes (una a una para no saturar la VM)"
for svc in vision ollama migrate frontend; do
  "${COMPOSE[@]}" build "$svc"
done
docker image inspect postgres:18.7-alpine3.24 >/dev/null 2>&1 || docker pull postgres:18.7-alpine3.24
info "Descargando el modelo multimodal (solo en esta fase)"
"${COMPOSE[@]}" --profile setup run --rm model-init
info "Registrando el manifiesto de modelos"
bash scripts/models-manifest.sh
info "Generando documentos sintéticos de ejemplo"
docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test build system-tests
docker run --rm --user "$(id -u):$(id -g)" -v "$ROOT/examples/generated":/out vie/tests:1.0.0 \
  python -m synthetic.generate --out /out --pdf --camera
ok "Instalación completa. Inicie el sistema (sin Internet) con: make up"
