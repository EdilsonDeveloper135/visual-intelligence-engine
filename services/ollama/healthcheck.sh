#!/bin/sh
# Healthy only when the server answers AND the configured model is installed.
set -eu
MODEL="${VIE_VLM_MODEL:-}"
if [ -z "$MODEL" ]; then exec /bin/ollama list >/dev/null; fi
/bin/ollama show "$MODEL" >/dev/null 2>&1
