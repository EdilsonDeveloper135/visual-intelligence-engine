#!/bin/sh
# INSTALL PHASE ONLY: starts a temporary Ollama server and pulls the configured
# models into the shared volume. Runs on the "setup" network (Internet allowed).
set -eu
MODELS="${VIE_VLM_MODELS_TO_PULL:-qwen3-vl:2b-instruct}"
/bin/ollama serve >/tmp/ollama-serve.log 2>&1 &
PID=$!
i=0
until /bin/ollama list >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 90 ]; then echo "ollama did not start" >&2; cat /tmp/ollama-serve.log >&2; exit 1; fi
  sleep 1
done
for m in $(echo "$MODELS" | tr ',' ' '); do
  echo ">> pulling $m"
  /bin/ollama pull "$m"
done
echo ">> installed models:"
/bin/ollama list
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
