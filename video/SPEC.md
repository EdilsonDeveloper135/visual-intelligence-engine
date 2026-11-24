# SPEC — «Una factura, de foto a dato verificado»

GOAL:    al terminar, quien mira entiende que el VIE no se fía de una sola lectura: cruza OCR, QR, cuentas y modelo, y muestra la evidencia de cada dato.
OUTPUT:  HyperFrames 0.9.88, 1920 x 1080, 30 fps, español, sin audio (deliberado, ver REVIEW.md).
TIME:    62 s x 30 fps = 1860 fotogramas.
LOOK:    suelo = mesa #E4E8EC plano, sin textura; papel #FBFCFD; tinta #1D2733; tinta suave #4A5868.
         Acentos con significado fijo: azul #2F5DD0 = evidencia / lo que el motor lee; verde #2E7D5B = comprobación correcta;
         rojo #C8323C = error o discrepancia; ámbar #A86C12 = advertencia. Una sola pantalla azul completa: el título.
         Tipografía de la app: Atkinson Hyperlegible Next (700 títulos 72-116 px, tracking -1 %; 500-600 texto 34-44 px)
         y Atkinson Hyperlegible Mono 500 solo para valores reales (RUC, montos) a 40-92 px.
         Medio: la propia interfaz del producto (cajas de evidencia de 3 px, esquinas de 2 px) sobre fotos y capturas reales;
         sombra de contacto 0 18 px 40 px rgba(29,39,51,.22), radio 10-12 px en fotos y capturas.
OBJECTS: la foto real de la factura sintética (assets/data/photo.jpg), la imagen enderezada (processed.jpg),
         las 43 cajas OCR reales, la caja del QR real, los valores reales de la observación 773302c9
         y 4 capturas reales de la app (assets/ui/). Nada dibujado que tenga fuente real.
MOTION:  llegadas expo.out / power4.out 0.35-0.6 s; cámara power2.inOut 0.9-1.2 s; salidas power3.in 0.2-0.3 s;
         palabras con blur 6-8 px -> 0, 0.067 s entre palabras; cajas OCR 0.06 s de escalonado;
         un movimiento protagonista por plano; los títulos aterrizan y quedan quietos.
SHOTS:
  hook      0-12 s   La foto sobre la mesa; «Una foto de una factura» / «¿Qué dice? ¿Y cómo sabes que es cierto?».
                     4.2 s la cámara entra a la cabecera; un modelo local responde «RUC del emisor 20908301669»;
                     caja roja sobre el RUC del cliente, caja azul sobre el del emisor; el número se tacha;
                     «Leyó bien el número, pero en el campo equivocado». Salida: iris azul desde el número tachado.
  reveal   12-16 s   Pantalla azul: «Visual Intelligence Engine» / «No se fía de una sola lectura». Salida: la mesa sube.
  read     16-25 s   «Primero, endereza la foto»: el cuadrilátero real se dibuja y la hoja se endereza a su sitio.
                     «Después, lee cada línea»: 43 cajas en orden de lectura, contador hasta 43; «1,0 s».
  verify   25-38 s   «Lee también el código QR»: caja del QR y sus 6 datos (emisor en azul).
                     «Y hace las cuentas sin el modelo»: 109.00 + 19.62 = 128.62 vuelan desde sus cajas; IGV 18 %,
                     módulo 11, QR = impreso; «28 comprobaciones: 25 correctas y 3 advertencias».
  conflict 38-48 s   «¿Y el error del modelo?»: tres lecturas del RUC del emisor (QR, OCR+reglas, modelo en rojo);
                     «Se queda el valor del QR y te pide revisarlo». La hoja se abre en la captura real
                     de la pestaña Campos con la fila roja; punch-in a la fila. Salida: látigo a la izquierda.
  app      48-56 s   Tres capturas reales con látigo entre ellas: cámara, preguntar, explorar.
  end      56-62 s   «Corre en tu computadora.» «Sin Internet. Sin nube.» «Cada dato, con su evidencia.» + repo y comandos.
BANNED:  suelo oscuro con elementos flotando; brillo, partículas, degradados morados; papel crema con serif;
         etiquetas en mayúsculas pequeñas; tres tarjetas en fila; título sobre captura oscurecida; todo
         entrando con fade y subida; títulos que siguen moviéndose; logo en una esquina; cifras que la fuente no da.
QA:      t=1.5 foto + pregunta legible; t=7.8 cajas roja/azul sobre la foto con etiquetas; t=13.5 título;
         t=18.5 hoja a mitad del enderezado; t=22 cajas OCR + 43; t=27.5 QR y sus 6 datos; t=33 ecuación y filas;
         t=41.5 tres lecturas; t=46 captura con la fila roja; t=50/52.7/55.3 capturas; t=60 cierre completo.
