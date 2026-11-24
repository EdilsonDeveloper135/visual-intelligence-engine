# Manual de usuario — Mesa de verificación

## 1. Entrar

1. Inicie el sistema con `make up`.
2. Abra http://127.0.0.1:8765 en su navegador.
3. Escriba la clave de acceso (archivo `.env`, línea `VIE_ACCESS_KEY`). La sesión dura 12 horas.

El indicador inferior de la barra lateral muestra **Listo** cuando la base de datos, el motor de visión, el procesador y el modelo están operativos, y **Parcial** si falta alguno.

## 2. Leer un documento (Mesa)

1. En **Mesa**, arrastre una foto, un escaneo o un PDF sobre la hoja, o pulse **Elegir archivos**. Se aceptan PNG, JPEG, WEBP y PDF (hasta 20 MB por imagen, 30 MB y 30 páginas por PDF). Varias imágenes a la vez se registran como una secuencia.
2. En 1–2 segundos verá el texto leído (**Texto listo**). El modelo multimodal completa la interpretación en unos 30–60 segundos (**Interpretando** → **Completado**).
3. Marque **Solo lectura** si no necesita el modelo: es mucho más rápido y sigue verificando los datos.

### El visor (izquierda)

- **Zoom** con los botones o Ctrl/Cmd + rueda; arrastre para mover; **Rotar 90°**.
- **Capas**: texto leído (azul), campos verificados (verde), por revisar (rojo discontinuo), códigos QR (rosa).
- **Texto**: superpone el texto reconocido sobre la imagen para compararlo letra por letra.
- **Región**: dibuje un rectángulo para preguntar solo sobre esa zona o copiar su texto.
- **Ver sin corregir**: alterna entre la imagen corregida (perspectiva, enderezado) y la copia sin corregir. El original subido se conserva intacto y se puede descargar.
- Las etiquetas superiores muestran nitidez, brillo, contraste, resolución y las correcciones aplicadas. Son mediciones heurísticas, no probabilidades.

### El libro de verificación (derecha)

| Pestaña | Qué muestra |
|---|---|
| Resumen | Tipo de documento, descripción del modelo, conteo de verificaciones, tiempos, modelo y motor OCR. Botones **Interpretar de nuevo**, **Revalidar** y **Confirmar registro**. |
| Campos | Cada dato con su marca: ✓ confirmado (QR o varias fuentes), · leído con evidencia, ? requiere revisión, ✎ corregido por una persona. Pase el cursor para ver la evidencia en la imagen. El lápiz permite corregir. |
| Ítems | Líneas del comprobante. |
| Texto | Todo el texto reconocido con su identificador (`r_0012`) y la confianza del reconocedor (no es una probabilidad). |
| Objetos y relaciones | Entidades (emisor, cliente, RUC…), objetos vistos por el modelo (✓ si un detector lo confirma), relaciones e inferencias. |
| Validación | Verificaciones independientes del modelo: correctas, advertencias, fallas y «sin datos» (nunca se cuenta como correcto). |
| Revisión | Lo que necesita una persona: confirme el valor si coincide con la imagen o corríjalo. |
| Preguntar | Chat sobre la imagen. Las respuestas separan «Observado» de «Inferido» y pueden citar regiones. |
| JSON | El resultado completo, para copiar o descargar. |

### Cómo leer el estado de verificación

- **Verificado**: todas las comprobaciones posibles fueron correctas.
- **Con advertencias**: hay algo que mirar (por ejemplo, el modelo leyó un valor distinto al QR, o la tasa de IGV no es una de las configuradas).
- **Inconsistente**: falla una regla del documento (por ejemplo, la suma no da el total impreso).
- **Datos insuficientes**: no hay datos para verificar.

El QR de la factura electrónica y las reglas tienen prioridad sobre el modelo; si el modelo discrepa, el campo pasa a revisión pero el documento no se declara inconsistente por un error de lectura del modelo.

## 3. Cámara

1. En **Cámara**, pulse **Activar cámara** y acepte el permiso del navegador. En macOS, el navegador también necesita permiso en Ajustes del Sistema → Privacidad y seguridad → Cámara.
2. Elija cámara, resolución y cada cuánto capturar.
3. Coloque un documento frente a la cámara. El sistema espera a que la imagen esté estable, elige el fotograma más nítido y lo registra como **observación nueva**. Si mueve el documento o mejora mucho la nitidez, se registra una **actualización**. Si nada cambia, no se vuelve a analizar (**repetida**).
4. Por defecto la cámara solo lee texto (rápido). Pulse **Interpretar con el modelo** para enviar la última observación al modelo multimodal. En Ajustes → Cámara puede activar la interpretación automática con un intervalo mínimo.

## 4. Explorar, comparar y exportar

- **Explorar**: busque por texto, RUC, serie o emisor; filtre por tipo, verificación, origen o revisión pendiente.
- Seleccione registros para **exportar** (CSV, CSV de ítems, Excel, JSON, informe HTML). Sin selección se exportan los resultados del filtro.
- Seleccione exactamente dos para **Comparar**: muestra diferencias de campos y avisa si parecen duplicados.
- **Mover a la papelera** pide escribir ELIMINAR; desde la papelera se puede **Restaurar** o **Vaciar** (permanente, también con confirmación).

## 5. Historial

Miniaturas por día de todo lo observado, con marcas de cámara, actualizaciones y cuántas veces se vio la misma escena, más la tabla de sesiones de cámara.

## 6. Ajustes

- **Modelos**: modelos instalados y cuál está activo. Instalar modelos nuevos requiere Internet y se hace con `make pull-model MODEL=…`.
- **Cámara**: intervalos y umbrales de escena repetida/nueva, interpretación automática.
- **Esquemas de extracción**: esquemas integrados (factura, boleta, recibos genéricos, universal) y creación de esquemas propios con sus campos y tipos.
- **Almacenamiento**: uso, cuota, política de conservación y papelera.
- **Auditoría**: registro de operaciones.
- **API**: documentación interactiva local.

## 7. Buenas prácticas

- Fotografíe el documento entero, de frente, con buena luz: mejora el OCR y la detección del QR.
- Revise siempre los campos marcados con «?» antes de usar los datos.
- Use **Confirmar registro** cuando haya revisado una observación.
- Haga respaldos periódicos con `make backup`.
