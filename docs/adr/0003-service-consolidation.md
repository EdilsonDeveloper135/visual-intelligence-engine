# ADR 0003 — Consolidación de servicios

- Estado: aceptado (2026-11-23)

## Decisión
- `vision` = vision-engine + ocr-engine (un solo proceso con OpenCV y ONNX en memoria).
- `worker` = misma imagen que `api` con otro comando.
- `inference`, `validation`, `extraction` = bibliotecas en proceso en `backend/vie/`.
- `document-processor` (Docling) = servicio opcional del perfil advanced.

## Motivo
Con 7,75 GB de VM compartida, duplicar OpenCV/ONNX/Python en varios contenedores cuesta cientos de MB sin aportar aislamiento útil. El aislamiento que sí importa se mantiene: quien decodifica archivos no confiables (`vision`) y el modelo (`ollama`) no tienen acceso a la base de datos ni a secretos.

La independencia de la validación es lógica, no física: el validador no recibe la opinión del modelo sobre la corrección, solo valores, y nunca devuelve «correcto» sin datos.
