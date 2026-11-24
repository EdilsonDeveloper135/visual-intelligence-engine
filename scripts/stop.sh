#!/usr/bin/env bash
# Stops the stack. Data volumes are NEVER removed by this script.
source "$(dirname "$0")/common.sh"
"${COMPOSE[@]}" down
ok "Detenido. Los datos se conservan en los volúmenes vie_pgdata, vie_files y vie_ollama."
