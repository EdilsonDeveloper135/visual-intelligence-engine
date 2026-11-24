#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
"${COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'
echo
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' $( "${COMPOSE[@]}" ps -q ) 2>/dev/null || true
