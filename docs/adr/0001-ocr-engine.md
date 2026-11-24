# ADR 0001 — Motor OCR: RapidOCR + modelos PaddleOCR (ONNX)

- Estado: aceptado (2026-11-23)

## Contexto
Se pidió usar PaddleOCR. El entorno es Docker Desktop en Apple Silicon: contenedores linux/arm64, solo CPU, VM de 7,75 GB compartida.

## Opciones
1. PaddleOCR 3.7 nativo sobre PaddlePaddle.
2. RapidOCR 3.10 (onnxruntime) con los mismos modelos PP-OCRv6/PP-OCRv5 exportados a ONNX.
3. Tesseract / EasyOCR.

## Decisión
Opción 2. `paddlepaddle` 3.3.x no publica wheels linux/aarch64 en PyPI (solo en un mirror externo), hay bugs abiertos en aarch64 (#78118, #18057) y `paddlex` fija `opencv-contrib-python==4.10` y `numpy<2.4`. RapidOCR tiene wheels aarch64 en PyPI, modelos < 100 MB verificables por SHA-256 y bajo consumo de memoria. Spike S2: 100 % de tokens clave y acentos en el conjunto sintético con PP-OCRv6 small en ~0,9 s.

## Consecuencias
Se conserva la calidad de los modelos de PaddleOCR sin su runtime. PP-StructureV3 (tablas complejas) no está disponible; se cubre con reglas de tabla, rapid-table (Hito 2) o Docling (perfil advanced).
