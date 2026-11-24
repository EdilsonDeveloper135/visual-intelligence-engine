# Visual Intelligence Engine

Plataforma local y privada que observa imágenes, documentos y la cámara, reconoce su contenido, lo interpreta con un modelo multimodal local, extrae datos estructurados, los **verifica de forma independiente** y los guarda en una memoria visual consultable. Pensada para comprobantes peruanos (facturas, boletas, notas de crédito, RUC, IGV, PEN/USD) y con un modo universal para documentos desconocidos.

Todo corre en Docker, sin GPU y sin servicios externos: después de la instalación funciona **sin Internet**.

## Qué hace

- Lee fotos, escaneos, capturas de pantalla y PDF (con texto incrustado o escaneados).
- Corrige perspectiva, inclinación e iluminación; mide la calidad de la imagen; conserva siempre el original.
- Reconoce texto (OCR PaddleOCR PP-OCRv6 vía RapidOCR), QR y códigos de barras, incluido el QR SUNAT.
- Interpreta la imagen con `qwen3-vl:2b-instruct` (Ollama): tipo de documento, descripción, campos, ítems, objetos y lo que no es legible; separa lo observado de lo inferido y deja `null` lo que no puede leer.
- Extrae campos con esquemas peruanos o en modo universal, cada uno con su evidencia (región OCR o QR) y su procedencia.
- Verifica sin el modelo: sumas, subtotales, IGV según la tasa observada, RUC (módulo 11), fechas, duplicados, coherencia QR/OCR/modelo e intentos de inyección de instrucciones.
- Guarda todo, permite buscar, comparar, corregir (con revisiones auditadas), preguntar sobre la imagen y exportar a JSON, CSV, Excel o informe HTML.
- Modo cámara: captura con permiso explícito del navegador, detecta escenas nuevas, actualizadas o repetidas y no re-analiza lo idéntico.

## Requisitos

- Docker Desktop (o Docker Engine) con Compose v2. Probado en macOS (Apple M4 Pro, contenedores linux/arm64).
- Perfil lite: unos **5 GB de RAM libres en la VM de Docker** y ~12 GB de disco.
- No necesita GPU. El override `docker-compose.gpu.yml` está disponible para NVIDIA, pero no se ha verificado en este equipo.

## Instalación (una vez, con Internet)

```bash
make install
```

Esto comprueba el entorno, crea `.env` con secretos aleatorios, construye las imágenes con dependencias fijadas, descarga el modelo multimodal (~1,9 GB) y genera documentos sintéticos de ejemplo en `examples/generated/`.

## Uso diario (sin Internet)

```bash
make up
```

Abra http://127.0.0.1:8765 e ingrese la clave de acceso, que está en `.env` como `VIE_ACCESS_KEY`. El puerto se cambia con `VIE_PORT`.

```bash
make down
```

`make down` detiene el sistema sin borrar datos.

## Comandos

| Comando | Para qué |
|---|---|
| `make status` | Estado y consumo de cada servicio |
| `make logs S=worker` | Ver registros de un servicio |
| `make test-unit` | Pruebas unitarias (backend, visión, frontend) en contenedores sin red |
| `make test-system` / `make test-system-all` | Pruebas contra el sistema en marcha (la segunda incluye el modelo) |
| `make test-e2e` | Pruebas en navegador con cámara simulada |
| `make test-recovery` / `make test-persistence` | Recuperación ante fallos y persistencia tras reinicio |
| `make verify-isolation` / `make verify-offline` | Endurecimiento de contenedores y ausencia de Internet en ejecución |
| `make backup` / `make restore BACKUP=…` | Respaldo y restauración |
| `make pull-model MODEL=…` | Descargar otro modelo (fase de instalación) |

## Documentación

- [Manual de usuario](docs/user-manual.md)
- [Arquitectura](docs/architecture.md) y [decisiones (ADR)](docs/adr/)
- [Investigación técnica y spikes](docs/research.md)
- [API](docs/api.md) (documentación interactiva local en http://127.0.0.1:8765/docs/)
- [Operación y mantenimiento](docs/operations.md)
- [Respaldo y restauración](docs/backup-restore.md)
- [Informe de seguridad](docs/security-report.md)
- [Informe de pruebas](docs/test-report.md)
- [Limitaciones conocidas](docs/limitations.md)

## Privacidad

Las imágenes y los datos nunca salen del equipo: los servicios internos no tienen salida a Internet, la telemetría está desactivada y la interfaz solo escucha en `127.0.0.1`. Los documentos de ejemplo son sintéticos y ficticios.

## Licencias de terceros

Qwen3-VL (Apache-2.0), Ollama (MIT), RapidOCR (Apache-2.0) con modelos PaddleOCR (Apache-2.0), onnxruntime (MIT), OpenCV (Apache-2.0), zxing-cpp (Apache-2.0), pypdfium2 (Apache-2.0/BSD-3), FastAPI (MIT), PostgreSQL (PostgreSQL License), React (MIT), fuentes Atkinson Hyperlegible (OFL-1.1). Detalle en [docs/research.md](docs/research.md).
