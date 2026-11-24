# Informe de seguridad

Alcance: Visual Intelligence Engine 1.0.0, perfil lite, Docker Desktop en macOS (linux/arm64). Las verificaciones automáticas se ejecutan con `make verify-isolation`, `make verify-offline` y las pruebas de `tests/system/test_security_api.py`; sus resultados reales están en `docs/test-report.md`.

## 1. Modelo de amenazas (resumen)

| Activo | Amenaza | Mitigación |
|---|---|---|
| Documentos e imágenes del usuario | Fuga a terceros | Procesamiento 100 % local; redes internas sin salida; telemetría desactivada; sin APIs de pago. |
| Equipo anfitrión | Contenedor comprometido | Sin `privileged`, sin `docker.sock`, `cap_drop: ALL`, `no-new-privileges`, usuarios no root, raíz de solo lectura, límites de memoria/CPU/procesos. |
| Base de datos | Archivo malicioso que compromete el decodificador | La decodificación ocurre solo en `vision`, que no tiene red hacia `postgres` ni secretos. |
| Integridad de los datos extraídos | Modelo que inventa, o texto del documento que da órdenes | Salida forzada a JSON Schema; fusión con prioridad QR > reglas > modelo; anclaje a evidencia; validación determinista independiente; revisión humana. |
| Acceso a la interfaz | Otras personas en la red local / sitios web maliciosos | Publicación solo en `127.0.0.1`; clave de acceso; sesión en servidor con cookie `HttpOnly`/`SameSite=Strict`; verificación exacta de `Origin`; lista de hosts permitidos. |
| Registros | Borrado accidental o malicioso | Borrado en dos pasos con token HMAC de corta duración y confirmación tecleada; papelera; auditoría. |

## 2. Aislamiento y privilegios

Comprobado por `scripts/verify-isolation.sh` en cada contenedor en ejecución:

- No privilegiado; todas las capacidades eliminadas y ninguna añadida; `no-new-privileges`.
- Sistema de archivos raíz de solo lectura; directorios temporales en `tmpfs` de tamaño limitado.
- Usuarios: 10001 (api, worker, vision, ollama), 70 (postgres), 101 (nginx).
- Sin el socket de Docker montado.
- Límites de memoria y de número de procesos en todos los servicios.
- Único puerto publicado: `127.0.0.1:8765` (frontend). Ninguna dirección `0.0.0.0`.
- Redes `vie_app`, `vie_core`, `vie_ml` internas; `vision` y `ollama` sin acceso a `vie_core` (base de datos).

**Riesgo aceptado:** el contenedor `frontend` está además en la red `edge`, que tiene puerta de enlace, porque Docker necesita una red no interna para publicar un puerto. nginx no inicia conexiones salientes (solo resuelve `api` con el DNS interno), no guarda datos ni secretos y corre sin root y en solo lectura.

## 3. Sin Internet en ejecución

`scripts/verify-offline.sh` intenta, desde api, worker, vision, ollama y postgres: TCP a 1.1.1.1:443 y 8.8.8.8:53, resolución DNS de example.com, `host.docker.internal:8080` (otros servicios del Mac) y `registry.ollama.ai`. Todo debe fallar, y después ejecuta un documento completo (OCR + modelo + validación) que debe terminar correctamente.

La descarga de modelos solo ocurre en la fase de instalación, en el servicio `model-init` (perfil `setup`), conectado a una red separada.

## 4. Control de acceso local

- Clave de acceso aleatoria (24 caracteres) generada en la instalación; comparación en tiempo constante; límite de 10 intentos fallidos por minuto.
- Sesión en servidor: solo se guarda el SHA-256 del token; expira a las 12 h; se rota al iniciar sesión; cookie `vie_session` `HttpOnly; SameSite=Strict; Path=/`.
- Las cookies no aíslan puertos en `127.0.0.1`. Por eso toda petición que modifica datos y el handshake del WebSocket exigen un `Origin` exactamente igual a `http://127.0.0.1:<puerto>` o `http://localhost:<puerto>`, y se rechaza `Sec-Fetch-Site: cross-site`.
- Anti DNS-rebinding: nginx cierra la conexión (444) para cualquier `Host` distinto de 127.0.0.1/localhost, y la API vuelve a comprobarlo.

## 5. Archivos no confiables

- El tipo se detecta por magic bytes; la extensión y el tipo declarado no se usan para decidir. Se rechazan SVG, HTML, XML, GIF, ejecutables y HEIC (no soportado). Si la extensión no coincide con el contenido real, el archivo se rechaza.
- Límites antes de decodificar: tamaño por tipo, número de archivos, píxeles (`Image.MAX_IMAGE_PIXELS`, `OPENCV_IO_MAX_IMAGE_PIXELS`, comprobación en la cabecera) para frenar bombas de descompresión, páginas de PDF, tiempo por job.
- La decodificación ocurre solo en `vision` (aislado). Se aplica la orientación EXIF y se re-codifica una **copia de trabajo sin metadatos** (EXIF/GPS/ICC). Las imágenes que se muestran son esas copias; el original subido se conserva inmutable (SHA-256, permisos 0440) y solo se entrega como descarga (`Content-Disposition: attachment`) con `nosniff` y una CSP `sandbox`.
- Rutas de archivo generadas por el sistema (hash/UUID); el nombre original solo se guarda saneado como metadato; toda ruta se resuelve y se comprueba que queda dentro del directorio de datos.

## 6. Inyección de instrucciones en documentos

- El texto del documento se envía al modelo entre delimitadores con un *nonce* aleatorio y declarado como datos no confiables; el prompt de sistema prohíbe obedecerlo.
- La salida del modelo está restringida a un JSON Schema y solo se trata como datos: no puede ejecutar acciones, no tiene herramientas ni acceso a la terminal, al sistema de archivos o a Docker.
- Los valores del modelo se sanean (caracteres de control, longitud máxima), se anclan a evidencia y no pueden reemplazar valores del QR o de las reglas.
- Un detector de patrones (es/en) marca textos con forma de instrucción («ignora las instrucciones», `SYSTEM:`, comandos de shell, órdenes de aprobar…) como advertencia y revisión humana. Probado con `factura_inyeccion.png`: el total inyectado («0.00») no altera el dato extraído.
- La interfaz nunca renderiza HTML del modelo ni de los documentos (React escapa el texto; el chat usa un renderizador mínimo sin HTML).

## 7. Motor de acciones

Nueve acciones en lista blanca (`save_record`, `export_json`, `export_csv`, `export_xlsx`, `classify_document`, `generate_report`, `compare_documents`, `search_records`, `create_alert`), con parámetros Pydantic estrictos (`extra="forbid"`). Un nombre desconocido devuelve 404 y queda auditado como denegado. Ninguna acción ejecuta comandos ni accede a la red. Solo el usuario puede invocarlas.

## 8. Exportaciones

Las celdas de CSV/XLSX que empiezan por `=`, `+`, `-` (no numérico), `@`, tabulador o retorno de carro se prefijan con `'` para evitar la inyección de fórmulas en hojas de cálculo. El informe HTML escapa todo el contenido y lleva una CSP `default-src 'none'`.

## 9. Cabeceras y navegador

CSP sin orígenes externos (`default-src 'self'; script-src 'self'; connect-src 'self' ws://<host>`; `frame-ancestors 'none'`; `object-src 'none'`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy: camera=(self)`, `Cross-Origin-Opener-Policy: same-origin`. Fuentes, iconos y Swagger UI se sirven localmente (sin CDN). La cámara solo se activa con un clic del usuario y el permiso del navegador.

## 10. Secretos

Solo en `.env` (permisos 600, en `.gitignore`), generados al instalar. No hay secretos en el código ni en las imágenes. Los respaldos no incluyen `.env`.

## 11. Auditoría y conservación

`audit_log` registra inicios de sesión (incluidos los denegados), cargas, ediciones, análisis, preguntas, borrados, restauraciones, purgas, exportaciones, acciones, cambios de modelo y de configuración, y sesiones de cámara. `VIE_RETENTION_DAYS` permite purgar automáticamente la papelera; por defecto se conserva todo.

## 12. Riesgos residuales conocidos

- `frontend` en una red con puerta de enlace (necesario para publicar el puerto).
- Las dependencias de terceros (onnxruntime, OpenCV/FFmpeg, pdfium, Ollama/llama.cpp) pueden tener vulnerabilidades; se mitigan con aislamiento y versiones fijadas, y hay que actualizarlas periódicamente.
- Cualquier proceso del mismo usuario del Mac que conozca la clave de acceso puede usar la API local.
- El modelo de 2B puede describir mal una imagen; esas descripciones se marcan como generadas por el modelo y no se usan para validar.
