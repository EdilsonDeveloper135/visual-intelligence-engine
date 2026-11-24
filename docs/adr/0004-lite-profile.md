# ADR 0004 — Perfil lite con qwen3-vl:2b-instruct

- Estado: aceptado (2026-11-23)

## Contexto
El usuario decidió mantener Docker Desktop en 7,75 GB. No hay GPU accesible desde contenedores en macOS.

## Decisión
`qwen3-vl:2b-instruct` (q4_K_M, 1,9 GB) con `num_ctx=4096`, KV cache q8_0, flash attention, sin caché de prompts en RAM y 6 hilos, en un contenedor limitado a 3,25 GB.

## Evidencia (spike S1)
- Con 3 GB y sin flash attention: OOM (el codificador de visión reserva ~4,7 GB).
- Configuración final: ~30–60 s por imagen, pico anónimo 3 064 MiB, JSON válido, sin campos inventados en imágenes vacías.
- Errores de lectura del modelo (p. ej. RUC del cliente como emisor) → por eso QR y reglas tienen prioridad y toda discrepancia pasa a revisión humana.

## Consecuencias
Interpretación lenta y de precisión limitada; el sistema está diseñado para no depender ciegamente del modelo. Con más RAM: `qwen3-vl:4b-instruct` u `8b-instruct` (perfil advanced).
