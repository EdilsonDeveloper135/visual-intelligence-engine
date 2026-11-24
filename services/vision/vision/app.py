"""Internal vision engine API (reachable only on the internal `ml` network).

Endpoints take the raw file bytes as the request body (application/octet-stream).
All content is treated as untrusted: type is sniffed from magic bytes, size and
pixel limits are enforced, and decoding happens only here.
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from contextlib import asynccontextmanager

import cv2
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from . import __version__
from .assess import assess as assess_frame
from .codes import read_codes
from .config import get_settings
from .media import (IMAGE_TYPES, MediaError, decode_frame, decode_image, encode_jpeg, pdf_page_count,
                    render_pdf_page, sniff, to_bgr)
from .ocr import get_engine, reading_order
from .preprocess import preprocess
from .quality import measure

settings = get_settings()
logging.basicConfig(level=settings.log_level, format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("vision")
cv2.setNumThreads(max(1, settings.ocr_threads))
_heavy = threading.Semaphore(settings.max_concurrent_analyses)

try:
    import ctypes

    _libc = ctypes.CDLL("libc.so.6")
except OSError:  # pragma: no cover - non-glibc platforms
    _libc = None


def _release_memory() -> None:
    """Return freed heap pages to the OS after each heavy analysis (keeps RSS bounded)."""
    import gc

    gc.collect()
    if _libc is not None:
        _libc.malloc_trim(0)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    t0 = time.perf_counter()
    get_engine()  # load models at startup (fail fast if a model file is missing)
    log.info("ocr models loaded in %.2fs", time.perf_counter() - t0)
    yield


app = FastAPI(title="VIE vision engine (internal)", version=__version__, lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(MediaError)
async def media_error_handler(_request: Request, exc: MediaError):
    return JSONResponse(status_code=422, content={"code": exc.code, "message": str(exc)})


@app.exception_handler(Exception)
async def unexpected_error_handler(_request: Request, exc: Exception):
    log.exception("unexpected error: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"code": "vision_internal_error",
                                                  "message": "Error interno del motor de visión."})


async def _read_body(request: Request, limit_mb: int) -> bytes:
    limit = limit_mb * 1024 * 1024
    declared = request.headers.get("content-length")
    if declared and int(declared) > limit:
        raise HTTPException(413, detail={"code": "too_large", "message": "Archivo demasiado grande."})
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, detail={"code": "too_large", "message": "Archivo demasiado grande."})
        chunks.append(chunk)
    if not size:
        raise HTTPException(400, detail={"code": "empty", "message": "Cuerpo vacío."})
    return b"".join(chunks)


@app.get("/health")
def health():
    eng = get_engine()
    return {"status": "ok", "version": __version__, "ocr_engine": eng.engine_id}


@app.post("/v1/inspect")
async def inspect(request: Request):
    data = await _read_body(request, settings.max_upload_mb)
    mime = sniff(data)
    if mime == "application/pdf":
        return {"mime": mime, "kind": "pdf", "page_count": pdf_page_count(data)}
    if mime in IMAGE_TYPES:
        return {"mime": mime, "kind": "image", "page_count": 1}
    if mime == "image/heic":
        raise MediaError("unsupported_type", "HEIC/HEIF no está soportado en esta versión; exporte la foto como JPEG.")
    raise MediaError("unsupported_type", "Tipo de archivo no soportado (se aceptan PNG, JPEG, WEBP y PDF).")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _analyze_sync(data: bytes, page: int, do_preprocess: bool, do_ocr: str, ocr_size: str | None,
                  ocr_variant: str | None) -> dict:
    timings: dict[str, int] = {}
    t = time.perf_counter()
    mime = sniff(data)
    if mime == "application/pdf":
        pg = render_pdf_page(data, page)
    elif mime in IMAGE_TYPES:
        if page != 0:
            raise MediaError("page_out_of_range", "Una imagen solo tiene la página 0.")
        pg = decode_image(data)
    else:
        raise MediaError("unsupported_type", "Tipo de archivo no soportado.")
    work = to_bgr(pg.image)
    timings["decode_ms"] = round((time.perf_counter() - t) * 1000)

    t = time.perf_counter()
    q_work = measure(work)
    timings["quality_ms"] = round((time.perf_counter() - t) * 1000)

    t = time.perf_counter()
    if do_preprocess and mime != "application/pdf":
        pre = preprocess(work, q_work["flags"])
    else:
        from .preprocess import Preprocessed
        pre = Preprocessed(image=work, steps=[{"name": "preprocessing", "applied": False,
                                                "reason": "disabled" if not do_preprocess else "pdf_render"}])
    processed = pre.image
    q_proc = measure(processed) if pre.changed else q_work
    timings["preprocess_ms"] = round((time.perf_counter() - t) * 1000)

    text_layer_chars = sum(len(x["text"]) for x in pg.text_layer)
    run_ocr = do_ocr == "always" or (do_ocr == "auto" and text_layer_chars < 30)
    ocr_out = {"engine": None, "lines": [], "rows": [], "skipped": not run_ocr,
               "skip_reason": "pdf_text_layer" if not run_ocr and do_ocr == "auto" else None}
    if run_ocr:
        t = time.perf_counter()
        eng = get_engine(ocr_size, ocr_variant)
        lines, _ = eng.run(processed)
        ocr_out = {
            "engine": eng.engine_id, "det_model": eng.det_name, "rec_model": eng.rec_name,
            "score_source": f"rapidocr:{eng.rec_name} (recognizer confidence, not calibrated)",
            "lines": [{"text": ln.text, "polygon": ln.polygon, "bbox": ln.bbox, "score": ln.score} for ln in lines],
            "rows": reading_order(lines), "skipped": False, "skip_reason": None,
        }
        timings["ocr_ms"] = round((time.perf_counter() - t) * 1000)

    t = time.perf_counter()
    codes = read_codes(processed)
    if not codes and pre.changed:
        codes = [{**c, "on": "work_image"} for c in read_codes(work)]
    timings["codes_ms"] = round((time.perf_counter() - t) * 1000)

    t = time.perf_counter()
    images = {"work_jpeg_b64": _b64(encode_jpeg(work, 90)),
              "processed_jpeg_b64": _b64(encode_jpeg(processed, 90)) if pre.changed else None}
    timings["encode_ms"] = round((time.perf_counter() - t) * 1000)

    return {
        "page": page, "mime": mime,
        "source_size": [pg.source_width, pg.source_height], "work_size": [work.shape[1], work.shape[0]],
        "processed_size": [processed.shape[1], processed.shape[0]], "scale": pg.scale, "notes": pg.notes,
        "quality": {"work": q_work, "processed": q_proc},
        "preprocessing": {"steps": pre.steps, "transform": pre.transform, "document_quad": pre.document_quad,
                          "skew_angle": pre.skew_angle, "changed": pre.changed},
        "ocr": ocr_out, "codes": codes, "text_layer": pg.text_layer, "images": images, "timings": timings,
    }


@app.post("/v1/analyze")
async def analyze(request: Request, page: int = Query(0, ge=0, le=999), preprocess_image: bool = True,
                  ocr: str = Query("auto", pattern="^(auto|always|never)$"),
                  ocr_size: str | None = Query(None, pattern="^(small|medium)$"),
                  ocr_variant: str | None = Query(None, pattern="^(multi_v6|latin_v5)$")):
    data = await _read_body(request, settings.max_upload_mb)
    from starlette.concurrency import run_in_threadpool

    def job():
        with _heavy:
            try:
                return _analyze_sync(data, page, preprocess_image, ocr, ocr_size, ocr_variant)
            finally:
                _release_memory()

    t0 = time.perf_counter()
    result = await run_in_threadpool(job)
    result["timings"]["total_ms"] = round((time.perf_counter() - t0) * 1000)
    return result


@app.post("/v1/assess")
async def assess(request: Request):
    data = await _read_body(request, 8)
    from starlette.concurrency import run_in_threadpool

    def job():
        return assess_frame(decode_frame(data))

    return await run_in_threadpool(job)
