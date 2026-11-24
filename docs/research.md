# Investigación técnica y spikes (Fases 1–2)

Fecha de verificación: 2026-11-23. Fuentes: PyPI JSON API, npm registry, Docker Hub / GHCR / MCR / Quay manifests, GitHub API, documentación oficial de cada proyecto. Las mediciones de los spikes se hicieron en este equipo (Apple M4 Pro, Docker Desktop 4.100.1, VM linux/arm64 de 7,75 GiB compartida con otros stacks).

## 1. Entorno

| Recurso | Valor |
|---|---|
| CPU | Apple M4 Pro, 14 núcleos (todos visibles en la VM de Docker) |
| RAM host / VM Docker | 48 GB / **7,75 GiB** (≈1,8 GB ya usados por otros stacks del usuario) |
| GPU | No disponible en contenedores (Docker Desktop en macOS no expone Metal) → inferencia en CPU |
| Disco libre | 56 GB |
| Docker | Engine 29.9.3, Compose v5.7.1, arquitectura `linux/arm64` |

## 2. Proyectos analizados

| Proyecto | Versión verificada | Licencia | Decisión |
|---|---|---|---|
| [QwenLM/Qwen3-VL](https://github.com/QwenLM/Qwen3-VL) | pesos 2B/4B/8B Instruct y Thinking | Apache-2.0 (código y pesos) | **Usado** vía Ollama: `qwen3-vl:2b-instruct` (1,9 GB q4_K_M). Los tags sin sufijo (`qwen3-vl:2b`) son la variante *thinking*. Grounding en coordenadas relativas 0–1000 (`bbox_2d`). |
| [ollama/ollama](https://github.com/ollama/ollama) | 0.40.17 (2026-11-10) | MIT | **Usado** como runtime. Desde esta versión ejecuta un `llama-server` embebido y acepta variables `LLAMA_ARG_*`. Sin auto-actualización en Linux; `OLLAMA_NO_CLOUD=1`. |
| [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | v1.0.0 (2026-11-13) | MIT | **No usado directamente** (Ollama ya lo embebe). Alternativa documentada: `ghcr.io/ggml-org/llama.cpp:server` soporta Qwen3-VL (mtmd). |
| [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | 3.7.0 (PP-OCRv6 por defecto) | Apache-2.0 | **Modelos usados, motor nativo descartado**: `paddlepaddle` 3.3.x no publica wheels linux/aarch64 en PyPI (solo en el mirror paddlepaddle.org.cn), bugs abiertos en aarch64 (#78118 libgfortran x86 en el wheel; #18057 salida en ceros en Apple Silicon) y `paddlex` fija `opencv-contrib-python==4.10` y `numpy<2.4`. Se usan los mismos modelos PP-OCRv6/PP-OCRv5 exportados a ONNX. |
| RapidAI/RapidOCR | 3.10.0 + onnxruntime 1.32.0 | Apache-2.0 / MIT | **Usado** como motor OCR (wheels aarch64 en PyPI, modelos <100 MB con SHA-256). |
| [docling-project/docling](https://github.com/docling-project/docling) | 2.152.0; docling-serve 1.39.0 | MIT | **Opcional (perfil advanced)**: requiere torch (imagen 4,4 GB, 2–4 GB RAM) → no cabe junto al VLM en 7,75 GB. |
| [docling-project/docling-graph](https://github.com/docling-project/docling-graph) | 1.9.2 | MIT | **No incorporado**: proyecto joven, arrastra docling + LiteLLM. Se adopta la idea: plantillas Pydantic → entidades y relaciones con procedencia (página/caja). |
| [Usimian/live-vlm-webui](https://github.com/Usimian/live-vlm-webui) (copia de NVIDIA-AI-IOT/live-vlm-webui 0.4.0) | 0.4.0 | Apache-2.0 | **Solo idea de diseño**: webcam del navegador → muestreo de fotogramas → VLM. Usa WebRTC/aiortc; aquí basta `getUserMedia` + WebSocket con JPEG. |
| [opencv/opencv](https://github.com/opencv/opencv) | opencv-python-headless 4.14.0.94 (5.1 disponible) | Apache-2.0 | **Usado** (preprocesamiento, calidad, QR de respaldo, video). Se fija 4.14 por estabilidad de API. |
| [fastapi/fastapi](https://github.com/fastapi/fastapi) | 0.165.0 | MIT | **Usado** (API y servicio interno de visión). Su Swagger por defecto carga recursos desde jsDelivr → se autoaloja. |

Otras dependencias verificadas: zxing-cpp 3.1.1 (Apache-2.0), pypdfium2 5.15.2 (Apache-2.0/BSD-3), Pillow 13.0.0, Pydantic 2.14.4, SQLAlchemy 2.1.9, asyncpg 0.32.0, Alembic 1.20.1, uvicorn 0.54.0, PostgreSQL 18.7, nginx-unprivileged 1.30.6, React 19.3, Vite 8.3, Tailwind 4.3, Playwright 1.65.1.

### Hallazgos de privacidad
- **onnxruntime 1.32** incluye telemetría 1DS (avisa "Failed to persist telemetry device ID"). Se llama a `onnxruntime.disable_telemetry_events()` y, además, el contenedor `vision` no tiene salida de red.
- **Ollama 0.40** arranca `llama-server` con caché de prompts en RAM de hasta 8 GB por defecto (`--cache-ram`). Se desactiva con `LLAMA_ARG_CACHE_RAM=0` (también evita crecimiento de memoria).

## 3. Spike S1 — modelo multimodal en CPU dentro del límite de memoria

Configuración final: `qwen3-vl:2b-instruct`, `num_ctx=4096`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `LLAMA_ARG_CACHE_RAM=0`, `LLAMA_ARG_THREADS=6`, límite de memoria del contenedor 3,25 GB (3328 MiB), salida forzada con JSON Schema, `temperature=0`, `think=false`.

Evolución (factura sintética 724×1024):

| Intento | Resultado |
|---|---|
| Límite 3 GB, sin flash attention | **OOM**: el codificador de visión reserva ~4,7 GB de búfer de cómputo |
| Límite 3 GB, flash attention | OOM: memoria anónima ≈3,1 GB (LM 1,3 GB + visión 0,8 GB + KV 0,45 GB + búferes) |
| Límite 4 GB (medición) | OK, 83 s (prefill 42,6 s, generación 39,2 s); hilos sin alinear (llama-server veía 14 CPU con límite de 6) |
| **Límite 3,25 GB, KV q8_0, cache-ram 0, 6 hilos** | **OK, ~30 s por imagen**, pico anónimo 3 064 MiB, sin OOM |

Resultados con la configuración final (1024 px salvo indicación):

| Muestra | Tiempo | Tipo | JSON válido | Observaciones |
|---|---|---|---|---|
| factura limpia | 32 s | factura | sí | serie y total correctos; **RUC del emisor confundido con el del cliente** |
| factura limpia @1280 | 34 s | factura | sí | igual |
| factura foto con perspectiva | 29 s | factura | sí | total y serie incorrectos a 1024; serie correcta a 1280 |
| boleta | 33 s | boleta | sí | RUC, serie, fecha y total correctos |
| página en blanco | 28 s | no_documento | sí | **todos los campos null** (no inventa) |
| escena sin documento | 37 s | no_documento | sí | campos null; descripción imprecisa de la escena |

Conclusiones:
- **GO** con 2B en CPU: ~30 s por imagen, memoria acotada. Ollama impone `--image-min-tokens 1024`, así que reducir la imagen por debajo de ~1024 px no ahorra tiempo; se usa 1280 px para documentos y 1024 px para cámara.
- El modelo pequeño **comete errores de campo** (RUC emisor/cliente, totales en fotos) → la arquitectura no confía en él: QR SUNAT + reglas con dígito verificador + validación aritmética independiente + anclaje de cada valor a una región OCR + revisión humana.
- Memoria disponible en la VM con el modelo cargado: ~3,2 GB (`MemAvailable`).

## 4. Spike S2 — OCR en español (RapidOCR + modelos PaddleOCR)

Tokens clave buscados: RUC emisor, documento del cliente, serie-número, fecha, total, IGV e importes de cada ítem; palabras con tilde/ñ: ELECTRÓNICA, Emisión, Señor(es), Perú, Descripción.

| Muestra | PP-OCRv6 small | PP-OCRv6 medium | PP-OCRv5 latin | small sin preprocesar |
|---|---|---|---|---|
| factura limpia | 9/9 · 5/5 · 0,9 s | 9/9 · 5/5 · 4,4 s | 9/9 · 5/5 · 0,85 s | 9/9 · 5/5 |
| boleta | 8/8 · 5/5 · 0,9 s | 8/8 · 5/5 · 4,1 s | 8/8 · 5/5 · 0,8 s | 8/8 · 5/5 |
| rotada 7° (deskew aplicado) | 9/9 · 5/5 · 1,1 s | 9/9 · 5/5 · 5,4 s | 9/9 · 5/5 · 1,0 s | 9/9 · 5/5 |
| foto con perspectiva (corrección aplicada) | 9/9 · 4/5 · 0,7 s | 9/9 · 4/5 · 3,2 s | 9/9 · 4/5 · 0,6 s | 9/9 · 4/5 |
| desenfocada | 9/9 · 5/5 | 9/9 · 5/5 | 9/9 · 5/5 | 9/9 · 5/5 |
| poca luz | 9/9 · 5/5 | 9/9 · 5/5 | 9/9 · 5/5 | 9/9 · 5/5 |
| ruido + JPEG q35 | 9/9 · 5/5 | 9/9 · 5/5 | 9/9 · 5/5 | 9/9 · 5/5 |

El QR SUNAT se decodificó en todas las muestras (zxing-cpp).

Memoria del servicio `vision` (un motor cargado): primero hubo **OOM a 768 MiB** por fragmentación del heap entre peticiones de tamaño variable; con `MALLOC_ARENA_MAX=2`, `malloc_trim` tras cada análisis y lado máximo del detector 1600 px, el pico anónimo en 3 pasadas completas fue **483 MiB** sin OOM.

Conclusiones: **PP-OCRv6 small** por defecto (mismo acierto que medium, 4–5× más rápido). El conjunto sintético es fácil (tipografía renderizada); la precisión con fotos reales debe medirse con documentos reales del usuario — limitación documentada.

## 5. Decisiones derivadas

Ver `docs/adr/`. Resumen: Ollama + qwen3-vl:2b-instruct (lite), RapidOCR + PP-OCRv6 small, OpenCV 4.14, zxing-cpp, pypdfium2, FastAPI, PostgreSQL 18 como base de datos **y** cola (sin Redis), React + Vite, Docling solo en perfil advanced.
