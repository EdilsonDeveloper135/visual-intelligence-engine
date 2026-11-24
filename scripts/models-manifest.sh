#!/usr/bin/env bash
# Writes models/manifest.lock.json with the installed Ollama models and their digests.
source "$(dirname "$0")/common.sh"
"${COMPOSE[@]}" run --rm --no-deps --entrypoint sh model-init -c '
  /bin/ollama serve >/tmp/s.log 2>&1 & i=0
  until /bin/ollama list >/dev/null 2>&1; do i=$((i+1)); [ $i -gt 60 ] && exit 1; sleep 1; done
  /bin/ollama list' | awk 'NR>1 && NF {print $1" "$2" "$3$4}' > /tmp/vie-models.txt
{
  echo '{'
  echo '  "generated_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",'
  echo '  "runtime": "ollama/ollama:0.40.17",'
  echo '  "models": ['
  first=1
  while read -r name id size; do
    [ $first -eq 0 ] && echo ','
    printf '    {"name": "%s", "id": "%s", "size": "%s"}' "$name" "$id" "$size"
    first=0
  done < /tmp/vie-models.txt
  echo
  echo '  ],'
  echo '  "ocr_models": "baked into vie/vision:1.0.0 (see services/vision/build/fetch_models.py for SHA-256)"'
  echo '}'
} > models/manifest.lock.json
rm -f /tmp/vie-models.txt
ok "models/manifest.lock.json actualizado"
