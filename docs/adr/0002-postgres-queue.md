# ADR 0002 — PostgreSQL como base de datos y como cola de trabajos

- Estado: aceptado (2026-11-23)

## Contexto
La propuesta incluía Redis. La VM de Docker tiene ~5 GB útiles y el modelo usa 3,25 GB.

## Decisión
Cola durable en PostgreSQL: `UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED)` con *leases* renovados por heartbeat y `LISTEN/NOTIFY` para despertar al worker y difundir eventos.

## Consecuencias
- Un servicio menos (~100 MB) y el estado del job y de la observación se escriben en la misma transacción.
- Si el worker muere, el lease expira y otro worker reclama el job (probado en `scripts/test-recovery.sh`).
- Throughput limitado comparado con un broker dedicado; suficiente para un equipo local (el cuello de botella es el modelo).
