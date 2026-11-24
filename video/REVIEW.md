# REVIEW — «Una factura, de foto a dato verificado»

Render: `docs/media/vie-explicacion.mp4` — H.264, 1920×1080, 30 fps, 1 890 fotogramas, 63,0 s, 16,2 MB, sin pista de audio (verificado con ffprobe y con fotogramas decodificados a 0,5 / 7,8 / 22,5 / 41,5 / 46,5 / 61,5 s).

## Decisiones creativas

- Se construyó la storyline A de `STORYLINES.md` (ejemplo trabajado con una sola factura). No se construyeron B (antes y después tecleando en Excel) ni C (la factura que miente: total alterado + inyección de instrucciones).
- Todo lo que aparece es real: la foto y la imagen enderezada de la observación `773302c9-3e9b-467c-9111-7086889afd9a`, sus 43 cajas OCR, la caja del QR, sus 28 comprobaciones, el error real del modelo (RUC del cliente puesto como emisor) y 4 capturas de la app tomadas con Playwright. Las cajas sobre la foto original se proyectaron con la homografía del cuadrilátero real y se comprobó visualmente que caen sobre el texto.
- Tiempos medidos que se citan: OCR 1,0 s (`vision_ocr_ms`), 43 líneas, 28 comprobaciones (25 correctas, 3 advertencias).
- Look tomado de la propia interfaz (tokens de color y tipografía Atkinson Hyperlegible de la app); una sola pantalla de color completo (el título).
- Transiciones con causa: iris desde el número tachado, la mesa que sube, continuidad del documento entre escenas, la hoja que se abre en la captura real, látigos entre capturas y blur swap al cierre.

## Medido y solo mirado

- Medido: `hyperframes check` sin errores (el aviso de contraste se corrigió); ffprobe del archivo final.
- Mirado: hoja de beats, 6 costuras, hoja a 360 px de ancho, 13 fotogramas puntuales y 6 fotogramas decodificados del MP4.
- Nadie lo vio en tiempo real de principio a fin a velocidad normal; el ritmo se juzgó por los tiempos de lectura (0,5 s + 0,3 s por palabra) y las hojas.

## Avisos que se mantienen a propósito

- `film_silent`: sin sonido deliberado. GitHub reproduce los videos sin sonido y no había fuente de música local; añadir música está explicado en el README.
- `container_overflow` / `escaped_container` (info): son los zooms de cámara y los números que vuelan desde la hoja; intencionales.

## Plano más débil y qué cambiaría

- En el teléfono (360 px) los textos de detalle de 34-38 px quedan pequeños; los títulos sí se leen. Con más tiempo: subir los detalles a 44 px o quitarlos en una versión vertical.
- El enderezado (18-19 s) es una aproximación visual: la hoja corregida aparece sobre el cuadrilátero y rota a su sitio; no es la deformación de perspectiva real fotograma a fotograma.
