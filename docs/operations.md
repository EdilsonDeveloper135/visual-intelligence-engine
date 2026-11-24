# Operación y mantenimiento

## Fases

| Fase | Internet | Comando | Qué ocurre |
|---|---|---|---|
| Instalación | Sí (autorizada) | `make install` | Comprueba Docker/RAM/disco, crea `.env` (secretos aleatorios, permisos 600, nunca sobrescribe), construye imágenes desde lockfiles, hornea los modelos OCR (SHA-256), descarga el modelo multimodal con `model-init`, escribe `models/manifest.lock.json`, genera ejemplos sintéticos. |
| Ejecución | No | `make up` | `docker compose up -d --pull never --no-build`: si falta una imagen falla en vez de descargarla. Los servicios internos no tienen salida a Internet. |

Las imágenes base están fijadas por etiqueta **y digest**; las dependencias Python por `uv.lock` y las de Node por `package-lock.json`. Para regenerar lockfiles (requiere Internet): `make lock`.

## Servicios

| Servicio | Imagen | Usuario | Memoria (lite) | Healthcheck |
|---|---|---|---|---|
| frontend | vie/frontend (nginx-unprivileged 1.30.6) | 101 | 48 MB | `wget /healthz` |
| api | vie/backend | 10001 | 288 MB | `/api/v1/health/live` |
| worker | vie/backend | 10001 | 320 MB | latido en `/tmp/worker-heartbeat` |
| vision | vie/vision | 10001 | 768 MB | `/health` |
| ollama | vie/ollama (ollama 0.40.17) | 10001 | 3,25 GB | `ollama show <modelo>` |
| postgres | postgres 18.7-alpine | 70 | 256 MB | `pg_isready` |
| migrate | vie/backend (one-shot) | 10001 | — | termina tras `alembic upgrade head` |

Todos: `cap_drop: ALL`, `no-new-privileges`, sistema de archivos raíz de solo lectura, límites de CPU/memoria/procesos, `memswap_limit` igual a la memoria, logs `json-file` rotados (10 MB × 3), `restart: unless-stopped`. `oom_score_adj` alto en los servicios VIE para que, si la VM se queda sin memoria, se sacrifiquen antes que otros contenedores del equipo.

## Configuración (`.env`)

Ver `.env.example`, comentado. Lo más habitual:

| Variable | Defecto | Efecto |
|---|---|---|
| `VIE_PORT` | 8765 | Puerto de la interfaz (solo en `VIE_BIND_ADDRESS`, por defecto 127.0.0.1) |
| `VIE_VLM_MODEL` | qwen3-vl:2b-instruct | Modelo por defecto (se puede cambiar en Ajustes → Modelos) |
| `VIE_VLM_NUM_CTX` / `VIE_VLM_NUM_PREDICT` | 4096 / 1024 | Contexto y longitud máxima de respuesta del modelo |
| `VIE_VLM_MAX_SIDE_DOCUMENT` | 1280 | Lado mayor de la imagen enviada al modelo |
| `VIE_OCR_MODEL_SIZE` | small | `medium` es 4–5× más lento (perfil advanced) |
| `VIE_MAX_IMAGE_MB`, `VIE_MAX_PDF_MB`, `VIE_MAX_PDF_PAGES` | 20, 30, 30 | Límites de carga |
| `VIE_STORAGE_QUOTA_GB` | 10 | Cuota de almacenamiento de archivos |
| `VIE_RETENTION_DAYS` | 0 | >0: purga automática de la papelera tras N días (0 = conservar todo) |
| `VIE_*_MEM`, `VIE_*_CPUS` | ver archivo | Límites de recursos por servicio |

Tras cambiar `.env`: `make restart`.

## Recursos y rendimiento medidos (lite, M4 Pro, VM 7,75 GB)

- OCR de una página A4: ~0,9–1,1 s; etapa 1 completa (decodificar + preprocesar + OCR + QR + reglas + validación): ~1–2 s.
- Interpretación con el modelo: ~28–60 s por imagen (prefill de ~2 600 tokens ≈ 25–40 s).
- Pico de memoria: ollama ~3,0 GB, vision ~0,5 GB, api/worker < 100 MB cada uno.

## Tareas habituales

| Tarea | Cómo |
|---|---|
| Ver estado y consumo | `make status`, pestaña *Recursos* de la consola o `GET /api/v1/system/status` |
| Ver registros | `make logs S=worker` (logs JSON estructurados) |
| Reintentar una interpretación | Botón **Interpretar de nuevo** o `POST /api/v1/observations/{id}/analyze` |
| Cambiar de modelo | `make pull-model MODEL=qwen3-vl:4b-instruct` (con Internet) y luego Ajustes → Modelos |
| Respaldar | `make backup` (ver `backup-restore.md`) |
| Verificar aislamiento | `make verify-isolation`, `make verify-offline` |
| Actualizar dependencias | Cambie versiones, `make lock`, `make install`, ejecute las pruebas |

## Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Indicador **Parcial** | Un servicio no está sano | `make status`; `make logs S=<servicio>` |
| Observaciones en **Parcial** con «sin interpretación» | Ollama caído, sin memoria o respuesta truncada | Revise `make logs S=ollama`; libere RAM en la VM; **Interpretar de nuevo** |
| `ollama` reiniciándose / `OOMKilled` | La VM no tiene memoria suficiente | Cierre otros contenedores o aumente la RAM de Docker Desktop; no baje `VIE_OLLAMA_MEM` de 3,25 GB con el modelo 2B |
| El puerto no abre | Puerto ocupado por otra aplicación | Cambie `VIE_PORT` en `.env` y `make restart` |
| La cámara no enciende | Permiso denegado en el navegador o en macOS | Permita la cámara para `127.0.0.1` y en Ajustes del Sistema → Privacidad → Cámara |
| `make up` falla con «image not found» | No se completó la instalación | Ejecute `make install` (con Internet) |

## Telemetría

Desactivada: `OLLAMA_NO_CLOUD=1`, `DO_NOT_TRACK=1`, `HF_HUB_OFFLINE=1`, `onnxruntime.disable_telemetry_events()`; además ningún servicio interno tiene salida a Internet. La caché de prompts en RAM de llama-server está desactivada (`LLAMA_ARG_CACHE_RAM=0`).
