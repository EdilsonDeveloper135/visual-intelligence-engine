# API interna

- Base: `http://127.0.0.1:8765/api/v1` (a través de nginx; la API no se publica directamente).
- Especificación OpenAPI: `/api/v1/openapi.json`. Documentación interactiva local: http://127.0.0.1:8765/docs/.
- Formato de error uniforme: `{"code": "...", "message": "...", "details": ...}`.
- Validación estricta: los cuerpos JSON rechazan campos desconocidos (`422 invalid_request`).

## Autenticación

```bash
curl -c cookies.txt -H 'Origin: http://127.0.0.1:8765' -H 'Content-Type: application/json' \
  -d '{"access_key":"<VIE_ACCESS_KEY>"}' http://127.0.0.1:8765/api/v1/auth/login
```

Las peticiones siguientes envían la cookie (`-b cookies.txt`). Toda petición que modifica datos debe llevar `Origin: http://127.0.0.1:8765` (o `http://localhost:8765`) o no llevar `Origin` (clientes que no son navegadores).

## Endpoints

| Método y ruta | Descripción |
|---|---|
| `POST /auth/login` · `POST /auth/logout` · `GET /auth/session` | Sesión local |
| `GET /health/live` | Vivo (sin sesión) |
| `GET /health/ready` · `GET /system/status` | Estado de BD, visión, modelo, worker, cola y recursos |
| `POST /observations` | Carga multipart (`files` repetible; `mode=full|ocr_only`; `schema_id`; `sequence=true`). Responde 202 con los ids |
| `GET /observations` | Historial con filtros `q`, `document_type`, `status`, `validation_status`, `source`, `ruc`, `camera_session_id`, `parent_id`, `date_from`, `date_to`, `needs_review`, `only_deleted`; paginación `page`, `page_size` |
| `GET /observations/{id}` | Detalle: resultado estructurado completo, archivos, estado |
| `GET /observations/{id}/regions` | Regiones con coordenadas: líneas OCR, códigos, campos |
| `GET /observations/{id}/history` | Revisiones humanas y eventos |
| `POST /observations/{id}/analyze` | Re-analizar (`stages: all|interpret`, `model`, `schema_id`) |
| `POST /observations/{id}/extract` | Extraer con un esquema concreto |
| `POST /observations/{id}/validate` | Re-ejecutar la validación |
| `PATCH /observations/{id}/fields` | Corregir campos/ítems/tipo (crea revisión y revalida) |
| `POST /observations/{id}/delete-request` → `DELETE /observations/{id}?confirm_token=` | Mover a la papelera (dos pasos) |
| `POST /observations/{id}/restore` | Restaurar de la papelera |
| `POST /trash/purge-request` → `DELETE /trash?confirm_token=` | Vaciar la papelera (permanente, dos pasos) |
| `GET /assets/{id}` | Imagen (copias re-codificadas en línea; el original como descarga) |
| `POST /observations/{id}/chat` · `GET /observations/{id}/chat` | Pregunta visual (respuesta por SSE) e historial |
| `GET /events/stream` | Server-Sent Events: progreso, resultados, deltas de chat (`observation_id` para filtrar) |
| `WS /camera/ws` | Cámara en tiempo real (fotogramas JPEG binarios; comandos JSON `analyze_now`, `stop`) |
| `GET /models` · `PUT /models/active` | Modelos instalados y activo |
| `GET /schemas` · `GET /schemas/{id}` · `POST /schemas` · `PUT /schemas/{id}` · `DELETE /schemas/{id}` | Esquemas de extracción (los integrados son de solo lectura) |
| `GET /settings` · `PUT /settings/camera` | Configuración |
| `GET /camera/sessions` | Sesiones de cámara y estadísticas |
| `POST /exports` | `format: json|csv|csv_items|xlsx|html` con `observation_ids` o `filters` |
| `GET /actions` · `POST /actions/{name}` | Acciones permitidas (`{"params": {...}}`) |
| `POST /compare` · `GET /search` | Comparar dos documentos; búsqueda en la memoria |
| `GET /alerts` · `POST /alerts/{id}/ack` | Alertas (p. ej. duplicados) |
| `GET /audit` | Registro de auditoría |
| `GET /storage` | Uso, cuota, conservación, papelera |

## Ejemplo: cargar y esperar el resultado

```bash
B=http://127.0.0.1:8765/api/v1; O='Origin: http://127.0.0.1:8765'
ID=$(curl -s -b cookies.txt -H "$O" -F files=@factura.jpg -F mode=full $B/observations | python3 -c 'import sys,json;print(json.load(sys.stdin)["observations"][0]["id"])')
curl -s -b cookies.txt $B/observations/$ID | python3 -m json.tool
```

## Estados de una observación

`queued` → `processing` → `ocr_ready` (texto, campos por reglas y validación preliminar disponibles) → `interpreting` → `completed`. `partial`: el modelo no pudo interpretar (resultado de OCR + reglas + validación conservado; se puede reintentar). `failed`: el archivo no pudo procesarse (motivo en `error`).

## Resultado estructurado

Ver `backend/vie/models/result.py`. Campos principales: `document_type` (+ `document_type_info` con lo que dijo cada fuente), `description`, `pages[]` (calidad y preprocesamiento), `text.lines[]` (id `r_0001`, caja, score con su origen), `codes[]` (QR con `parsed` SUNAT), `fields{}` (`value`, `raw`, `type`, `provenance` observed/computed/inferred, `source`, `sources[]`, `evidence_ids`, `bounding_box`, `needs_review`, `review_reasons`, `edited_by_human`), `dynamic_fields[]`, `items[]`, `entities[]`, `relationships[]`, `objects[]` (`verified`), `unreadable[]`, `inferences[]`, `validation{status, checks[], warnings[], needs_review[]}`, `metadata{model, model_digest, ocr_engine, pipeline_version, processing_time_ms, timings, vlm_tokens, vlm_status}`.
