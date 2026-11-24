# Limitaciones conocidas

## Precisión

- **Modelo de 2B en CPU.** Comete errores de lectura (en las pruebas confundió el RUC del cliente con el del emisor y leyó mal totales en fotos con perspectiva) y sus descripciones pueden ser imprecisas (describió una escena sin documento como «un icono con un ojo»). Por diseño, el QR y las reglas tienen prioridad, las discrepancias se marcan para revisión y la validación no depende del modelo. Más RAM permite `qwen3-vl:4b-instruct` u `8b-instruct`.
- **Citas en el chat:** el modelo 2B rara vez incluye las referencias `[r_0012]` aunque se le pide; las respuestas no siempre son verificables por región.
- **OCR medido sobre documentos sintéticos.** El 100 % de acierto en tokens clave corresponde a documentos generados con tipografía limpia (incluidas fotos degradadas simuladas). La precisión con fotos reales, papel térmico desvaído o escritura a mano no está medida; conviene evaluar con documentos reales del usuario.
- **Tablas complejas:** los ítems se extraen con reglas de tabla para comprobantes peruanos y con el modelo; no hay reconocimiento estructural de tablas arbitrarias (rapid-table/PP-Structure no están integrados en el perfil lite).
- **Objetos:** los objetos los reporta el modelo y solo los códigos QR/de barras se confirman con un detector; no hay cajas delimitadoras de objetos en el perfil lite.
- **Escritura a mano, sellos y firmas** no se interpretan de forma fiable.

## Rendimiento

- Interpretación con el modelo: ~30–60 s por imagen en este equipo (CPU). Un solo trabajo del modelo a la vez; las preguntas del chat esperan si hay una interpretación en curso.
- El modelo usa ~3 GB de RAM mientras está cargado (se mantiene 30 min tras el último uso).

## Funcionalidad

- **HEIC/HEIF** (fotos por defecto de iPhone) no se aceptan: exporte como JPEG. Motivo: las librerías disponibles incluyen códecs con licencias GPL/LGPL.
- **Video:** se extraen hasta 12 escenas (2 fotogramas por segundo, máximo 10 min y 100 MB). Cada escena es una observación independiente; no se interpreta el movimiento ni el audio.
- **Cámara:** dos documentos con el mismo diseño se distinguen leyendo su texto después del OCR, así que el cambio se confirma ~1–2 s después de la captura. Escenas sin texto (p. ej. un escritorio vacío) también se registran como observaciones.
- **PDF:** máximo 30 páginas; el modelo ve la primera página y el texto de todas (recortado al presupuesto de contexto).
- **Docling** (perfil advanced) está declarado como servicio opcional en `docker-compose.advanced.yml`, pero el pipeline aún no lo usa: no se pudo probar junto al modelo en la VM de 7,75 GB.
- **GPU NVIDIA:** `docker-compose.gpu.yml` no se ha verificado (el equipo de desarrollo no tiene GPU NVIDIA y Docker Desktop en macOS no expone Metal).
- **Esquemas peruanos especializados:** factura, boleta, nota de crédito/débito (esquema de factura) y un esquema genérico para recibos, comprobantes de pago, guías, órdenes de compra y cotizaciones. Guía de remisión, orden de compra y cotización no tienen campos propios (p. ej. punto de partida/llegada, transportista): use el modo universal o cree un esquema personalizado.
- **Tasas de IGV:** `configs/tax_rates.yaml` contiene 18 %, 10 % (régimen MYPE de restaurantes y hoteles; verificar vigencia) y 0 %. Una tasa fuera de la lista produce advertencia, no error. Mantenga la lista al día.
- **Usuarios:** un solo usuario local (clave de acceso compartida); no hay roles ni cuentas múltiples.

## Entorno y verificación

- Probado solo en macOS (Apple M4 Pro, Docker Desktop 4.100.1, linux/arm64). En linux/amd64 debería funcionar (todas las dependencias publican wheels/imágenes amd64), pero no se ha probado.
- La cámara física no se probó automáticamente: las pruebas usan el dispositivo simulado de Chromium con un video sintético. El flujo con cámara real requiere que una persona conceda el permiso en el navegador.
- Las pruebas E2E y de sistema necesitan un origen extra de prueba (`VIE_EXTRA_ORIGINS`, solo en `docker-compose.test.yml`) porque los ejecutores navegan por el puerto interno de nginx.
- El contenedor `frontend` está en una red con puerta de enlace (necesaria para publicar el puerto); los demás no tienen salida.
- Espacio en disco: las imágenes, el modelo y la caché de construcción ocupan ~15–20 GB en la VM de Docker.
