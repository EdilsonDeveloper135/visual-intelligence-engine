# Informe de pruebas

Ejecución final: 2026-11-24, 06:01–06:11 UTC, en el equipo de desarrollo (Apple M4 Pro, Docker Desktop 4.100.1, VM linux/arm64 de 7,75 GiB compartida con otros stacks). Registro completo: `tests/output/final-run.log` (se regenera con los comandos indicados; no se versiona). Ningún resultado de este informe es simulado: todos provienen de ejecuciones reales listadas abajo.

## Resumen

| Conjunto | Comando | Resultado |
|---|---|---|
| Unitarias backend (extracción, validación, cámara, seguridad) | `make test-unit` | **57 / 57** |
| Unitarias motor de visión (decodificación, calidad, preprocesamiento, OCR, QR, PDF, video, API interna) | `make test-unit` | **14 / 14** |
| Unitarias frontend (formato, renderizado seguro, prefiltro de cámara) | `make test-unit` | **5 / 5** |
| Sistema contra el stack real vía nginx (incluye las 3 que usan el modelo) | `make test-system-all` | **29 / 29** (154 s) |
| Extremo a extremo en navegador (Playwright, cámara simulada) | `make test-e2e` | **4 / 4** (40,6 s) |
| Aislamiento y endurecimiento de contenedores | `make verify-isolation` | **48 / 48** comprobaciones |
| Sin Internet en ejecución + pipeline completo offline | `make verify-offline` | **16 / 16** comprobaciones |
| Recuperación ante fallos | `make test-recovery` | **4 / 4** |
| Persistencia tras `docker compose down` + `make up` | `make test-persistence` | **correcta** (126 observaciones antes y después; imágenes accesibles) |
| Respaldo y restauración | `make backup` + `scripts/restore.sh … --yes` | **correcta** (126 → 126, SHA-256 verificado, respaldo de seguridad automático) |
| Instalador completo | `make install` | **correcto** (con imágenes en caché; `.env` existente respetado) |

> **Cambios posteriores a la batería final.** Tras revisar visualmente el panel de video se hicieron dos ajustes (ampliación de documentos pequeños tras corregir la perspectiva; los descuadres por ítem y de suma de ítems pasan de falla a advertencia con revisión). Después se volvieron a ejecutar: unitarias **76/76** (57 + 14 + 5), sistema rápido **26/26** y E2E **4/4**, todas correctas. No se repitieron tras ese cambio las pruebas lentas con el modelo, aislamiento, offline, recuperación ni persistencia; esos cambios no tocan la configuración de contenedores ni las rutas del modelo.

> **Cambio del 2026-11-24 (preparación del video).** Al procesar la foto con perspectiva de ejemplo, la respuesta del modelo se truncó (`done_reason: length`: el modelo agotó los 1 024 tokens de salida) y la observación quedó `partial`. Corrección: si la respuesta se trunca, se reintenta **una vez** con un esquema compacto (sin ítems, objetos, inferencias ni ilegibles, 640 tokens); los ítems siguen saliendo de las reglas OCR. Pruebas tras el cambio: unitarias **78/78** (59 + 14 + 5, dos nuevas: esquema compacto y reintento con el cliente de Ollama simulado) y sistema rápido **26/26**. La re-interpretación real de esa foto terminó `completed` en 28 s (772 tokens) **sin necesitar el reintento**, así que el camino del reintento solo está cubierto por la prueba unitaria. No se repitieron tras este cambio las pruebas con el modelo, E2E, aislamiento, offline, recuperación ni persistencia (el cambio no toca contenedores, red ni almacenamiento).

## Detalle

### Unitarias backend (57 + 2 del reintento compacto)
Normalización de montos/fechas/monedas peruanas; RUC (módulo 11, prefijos), DNI, serie-número y tipo por serie; QR SUNAT; importe en letras; extracción por reglas, QR y validación sobre **salidas OCR reales** del motor de visión para: factura limpia, rotada 7°, foto con perspectiva, boleta (IGV incluido), total incorrecto (detectado como inconsistente), régimen al 10 % (tasa observada, no asumida), documento con inyección de instrucciones (marcado, sin alterar datos), nota de crédito (documento que modifica), PDF digital (capa de texto, sin scores inventados), página en blanco (sin datos inventados); prioridad del QR sobre el modelo; discrepancias del modelo → revisión, no documento inválido; el modelo no puede autovalidarse; SceneTracker (nueva/actualizada/repetida, umbrales, regulación, documento con el mismo diseño y distinto contenido); detección de tipo por magic bytes (SVG/HTML/HEIC); path traversal; originales inmutables y direccionados por contenido; neutralización de fórmulas en CSV; lista blanca de acciones; detector de inyección.

### Unitarias de visión (14)
Magic bytes; orientación EXIF aplicada y metadatos eliminados; imágenes inválidas y bombas de descompresión rechazadas; desenfoque detectado; enderezado (±7°, y 0° en página recta); detección y corrección de perspectiva sin modificar el original; escaneo limpio sin cambios; OCR con tildes y RUC; QR SUNAT; PDF (capa de texto y render); evaluación rápida estable; video → 3 escenas (escritorio, factura, boleta); video inválido rechazado; endpoints internos.

### Sistema (29)
Seguridad: sesión obligatoria; clave incorrecta; `Origin` ajeno o de otro puerto local rechazado; `Sec-Fetch-Site: cross-site` rechazado; Host desconocido descartado; cabeceras CSP/X-Frame-Options/nosniff/Permissions-Policy; rechazo de SVG/HTML/GIF/EXE; extensión que no coincide; archivo de 21 MB → 413; bomba de 144 MP → `failed` con mensaje claro; nombre `../../../etc/passwd.png` saneado; borrado con token (ausente, inválido, de otra observación) y restauración; acciones no permitidas → 404 y parámetros extra → 422; validación estricta de entradas; auditoría; OpenAPI y `/docs/` locales; original como descarga y copia re-codificada sin EXIF.
Pipeline: lectura sola rápida y correcta en foto con perspectiva (< 60 s, original y copia procesada guardados); **pipeline completo con el modelo local** (OCR disponible antes que el modelo; tipo, descripción, total y documento del cliente correctos; todo valor con evidencia o marcado); inconsistencia detectada; inyección como datos; PDF digital; **página en blanco con el modelo: no inventa**; duplicados, búsqueda, alertas y comparación; edición humana con revisión y revalidación; exportación CSV/XLSX (3 hojas)/JSON/HTML sin `<script>`; **pregunta visual respondida** con el total; estado de modelos; **video → 3 escenas observadas, con factura y boleta leídas**.

### Extremo a extremo (4)
1. Clave incorrecta rechazada en la pantalla de acceso.
2. Carga de una factura desde la interfaz: navegación al resultado, > 20 regiones de texto y el QR dibujados sobre la imagen, RUC y serie visibles en Campos, corrección manual de «Forma de pago», verificación «Total verificado».
3. Explorador y descarga de CSV con el RUC esperado.
4. **Cámara con permiso** (dispositivo simulado de Chromium con un video sintético): se activa la cámara, se registran escenas nuevas y repetidas, y la **boleta aparece como observación nueva distinta de la factura** (cambio de documento con el mismo diseño detectado por el texto leído).

### Aislamiento (48) y sin Internet (16)
Ver `docs/security-report.md`. Todos los contenedores: no privilegiados, sin capacidades, `no-new-privileges`, raíz de solo lectura, usuario no root, límites de memoria y procesos, sin `docker.sock`; único puerto `127.0.0.1:8765`; redes internas; visión y modelo sin acceso a la base de datos. Sin Internet: fallan TCP a 1.1.1.1/8.8.8.8, DNS externo, `host.docker.internal` y `registry.ollama.ai` desde api, worker, vision, ollama y postgres; el pipeline completo con el modelo terminó correctamente sin red (28 s).

### Recuperación (4)
1. Ollama detenido → la observación queda `partial` en ~2 s con OCR, reglas y validación (boleta, total 161.00).
2. Al volver Ollama, «Interpretar de nuevo» la completa.
3. Worker eliminado con SIGKILL durante la interpretación → el job se reclama al expirar el lease y se completa.
4. Motor de visión detenido brevemente → la lectura se reintenta y se completa.

## Mediciones de rendimiento (este equipo, perfil lite)

| Medición | Valor |
|---|---|
| Etapa 1 (decodificar, preprocesar, OCR, QR, reglas, validación) — página A4 | media 815 ms, p95 1 171 ms |
| Interpretación con el modelo (20 observaciones) | media 41,5 s, mín. 25 s, máx. 64 s |
| Pregunta visual | ~45–50 s |
| Memoria en reposo (sin modelo cargado) | api 73 MB, worker 55 MB, vision 71 MB, postgres 40 MB, frontend 11 MB |
| Memoria pico del modelo | ~3,06 GB (límite 3,25 GB) |
| Memoria pico de visión en análisis | ~0,48–0,55 GB (límite 768 MB) |

## Defectos encontrados por las pruebas y corregidos

| Defecto | Detectado por | Corrección |
|---|---|---|
| OOM del modelo a 3 GB (búfer del codificador de visión ~4,7 GB) | spike S1 | flash attention, KV q8_0, sin caché de prompts, 6 hilos, límite 3,25 GB |
| OOM de visión por fragmentación del heap | spike S2 | `MALLOC_ARENA_MAX=2`, `malloc_trim`, lado máximo del detector |
| Telemetría de onnxruntime | spike S2 | `disable_telemetry_events()` + red interna |
| Modelo de clasificación de orientación con forma de entrada incorrecta | spike S2 | `cls_image_shape` del modelo PP-LCNet |
| Serie no detectada cuando el OCR une palabras («modificaF001-…») | unitarias | expresión regular tolerante |
| Discrepancia QR vs modelo marcaba el documento como inconsistente | prueba de sistema manual | advertencia + revisión (no falla del documento) |
| El modelo copiaba ejemplos del prompt («sello», «fecha borrosa») y rellenaba «documento que modifica» con la propia serie | prueba de sistema manual | prompt sin ejemplos copiables; guarda de fusión; verificación de objetos con el detector |
| Parámetros de acción inválidos → 500 | sistema | 422 con detalle |
| Cabeceras de seguridad duplicadas | sistema | `proxy_hide_header` en nginx |
| Ángulo de enderezado ~90° en página recta (convención de OpenCV 4.14) | unitarias de visión | normalización completa del ángulo |
| El prefiltro de cámara del navegador impedía estabilizar escenas | E2E | prefiltro solo cuando el servidor ya tiene la escena |
| Respuesta del modelo truncada (presupuesto de 768 tokens) | E2E | 1 024 tokens |
| Edición humana durante la interpretación se perdía | E2E (eventos) | releer el resultado actual + bloqueo de fila |
| Dos documentos con el mismo diseño se tomaban como la misma escena (cámara y video) | E2E + unitarias de video | firma de diseño normalizada + fusión/reetiquetado por texto OCR |
| Prueba E2E ejecutada con una imagen sin reconstruir (aserción antigua) | revisión del resultado | reconstrucción de la imagen y aserción más estricta (debe aparecer la boleta) |
| Documentos pequeños en fotogramas de video (~355×500 px) con ítems sin leer y errores de OCR que marcaban el documento como «Inconsistente» | revisión visual del panel de video | ampliación del documento tras corregir la perspectiva; los descuadres por ítem o por suma de ítems pasan a advertencia con revisión (la verificación base + IGV = total sigue siendo una falla) |

## Criterios de aceptación

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | Iniciarse mediante Docker Compose | Verificado | `make up`, `test-persistence` |
| 2 | Abrir una interfaz web local | Verificado | E2E, navegador integrado |
| 3 | Cargar una imagen real | Verificado con imágenes sintéticas realistas (fotos con perspectiva, ruido, poca luz) | E2E 2, sistema. **Pendiente:** fotos reales del usuario |
| 4 | Reconocer sus textos | Verificado | unitarias de visión, sistema |
| 5 | Interpretar su contenido con un modelo local | Verificado | `test_full_pipeline_with_local_model`, offline |
| 6 | Extraer datos estructurados | Verificado | unitarias, sistema |
| 7 | Mostrar visualmente las regiones reconocidas | Verificado | E2E 2 (cajas SVG) |
| 8 | Validar los campos extraídos | Verificado | unitarias, sistema |
| 9 | Guardar los resultados | Verificado | sistema, persistencia |
| 10 | Consultar observaciones anteriores | Verificado | búsqueda, explorador (E2E 3) |
| 11 | Responder preguntas sobre la imagen | Verificado | `test_visual_question_answering`, prueba manual en la UI |
| 12 | Exportar los datos | Verificado | `test_exports`, E2E 3 |
| 13 | Capturar imágenes desde una cámara autorizada | Verificado con cámara simulada | E2E 4. **Pendiente:** cámara física (requiere permiso humano) |
| 14 | Funcionar sin conexión después de la instalación | Verificado | `verify-offline` |
| 15 | Reiniciarse sin perder información | Verificado | `test-persistence`, respaldo/restauración |

## Pendiente / no verificable en este entorno

- Cámara física (las pruebas usan el dispositivo simulado de Chromium).
- Precisión con documentos reales del usuario (fotos de comprobantes reales, papel térmico, escritura a mano).
- GPU NVIDIA (`docker-compose.gpu.yml`) y perfil advanced con modelos 4B/8B y Docling (la VM de 7,75 GB no tiene memoria suficiente).
- Ejecución en linux/amd64.
- Navegadores distintos de Chromium (Firefox/Safari) para la interfaz y la cámara.
