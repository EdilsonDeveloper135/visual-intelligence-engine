"""Decoding of UNTRUSTED media (images, PDF, video).

This module runs only inside the isolated `vision` container (no network, no
database credentials, read-only filesystem). Every decoder enforces limits
before allocating large buffers.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps

from .config import get_settings

_settings = get_settings()
Image.MAX_IMAGE_PIXELS = _settings.max_image_pixels
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(_settings.max_image_pixels))


class MediaError(ValueError):
    """Raised for unsupported, malformed or oversized input. Message is safe to show."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Content sniffing (magic bytes). Extensions and declared types are never trusted.
# ---------------------------------------------------------------------------
def sniff(data: bytes) -> str | None:
    head = data[:64]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand == b"qt  ":
            return "video/quicktime"
        if brand in (b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis", b"avif"):
            return "image/heic"  # recognised but not supported in v1
        return "video/mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    return None


IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}


@dataclass
class Page:
    index: int
    image: Image.Image  # RGB work image (EXIF applied, metadata stripped, bounded size)
    source_width: int
    source_height: int
    scale: float  # work-image px per source px (or per PDF point for PDFs)
    text_layer: list[dict] = field(default_factory=list)  # PDF text lines with boxes in work-image px
    notes: list[str] = field(default_factory=list)


def _bounded(img: Image.Image, max_side: int) -> tuple[Image.Image, float]:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_side:
        return img, 1.0
    scale = max_side / longest
    return img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS), scale


def decode_image(data: bytes) -> Page:
    max_side = _settings.work_image_max_side
    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size  # header only, nothing decoded yet
        if w * h > _settings.max_image_pixels:
            raise MediaError("image_too_large", f"La imagen tiene {w}x{h} píxeles; supera el límite permitido.")
        notes = []
        if img.format == "JPEG" and max(w, h) > 2 * max_side:
            img.draft("RGB", (max_side, max_side))  # cheap DCT downscale for huge phone photos
            notes.append("jpeg_draft_downscale")
        img.load()
    except MediaError:
        raise
    except Image.DecompressionBombError as exc:
        raise MediaError("image_too_large", "La imagen supera el límite de píxeles permitido.") from exc
    except Exception as exc:  # noqa: BLE001 - any decoder error means invalid input
        raise MediaError("invalid_image", "El archivo no es una imagen válida o está dañado.") from exc

    orientation = img.getexif().get(0x0112, 1) if hasattr(img, "getexif") else 1
    img = ImageOps.exif_transpose(img)
    if orientation not in (1, None):
        notes.append(f"exif_orientation_{orientation}_applied")
    if img.mode not in ("RGB",):
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            bg = Image.new("RGB", rgba.size, "white")
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
    src_w, src_h = (h, w) if orientation in (5, 6, 7, 8) else (w, h)
    work, scale = _bounded(img, max_side)
    if scale != 1.0:
        notes.append("downscaled_to_work_size")
    # Re-create a clean image object: drops EXIF/ICC/XMP metadata from derived copies.
    clean = Image.frombytes("RGB", work.size, work.tobytes())
    return Page(index=0, image=clean, source_width=src_w, source_height=src_h,
                scale=work.width / src_w, notes=notes)


def pdf_page_count(data: bytes) -> int:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as exc:  # noqa: BLE001
        raise MediaError("invalid_pdf", "El PDF no es válido, está dañado o protegido.") from exc
    try:
        return len(pdf)
    finally:
        pdf.close()


def render_pdf_page(data: bytes, index: int) -> Page:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as exc:  # noqa: BLE001
        raise MediaError("invalid_pdf", "El PDF no es válido, está dañado o protegido.") from exc
    try:
        n = len(pdf)
        if n > _settings.max_pdf_pages:
            raise MediaError("too_many_pages", f"El PDF tiene {n} páginas; el máximo es {_settings.max_pdf_pages}.")
        if not 0 <= index < n:
            raise MediaError("page_out_of_range", "Página fuera de rango.")
        page = pdf[index]
        pw, ph = page.get_size()  # PDF points
        scale = _settings.pdf_render_dpi / 72.0
        longest = max(pw, ph) * scale
        if longest > _settings.work_image_max_side:
            scale = _settings.work_image_max_side / max(pw, ph)
        bitmap = page.render(scale=scale)
        pil = bitmap.to_pil().convert("RGB")
        text_layer = _pdf_text_layer(page, ph, scale)
        page.close()
        return Page(index=index, image=pil, source_width=round(pw), source_height=round(ph), scale=scale,
                    text_layer=text_layer, notes=[f"pdf_rendered_at_{round(scale * 72)}dpi"])
    finally:
        pdf.close()


def _pdf_text_layer(page, page_height: float, scale: float) -> list[dict]:
    """Text segments of a digital PDF with boxes converted to work-image pixels."""
    lines: list[dict] = []
    try:
        tp = page.get_textpage()
        for i in range(tp.count_rects()):
            left, bottom, right, top = tp.get_rect(i)
            text = tp.get_text_bounded(left, bottom, right, top).strip()
            if not text:
                continue
            x0, x1 = left * scale, right * scale
            y0, y1 = (page_height - top) * scale, (page_height - bottom) * scale
            lines.append({"text": text, "bbox": [round(x0), round(y0), round(x1), round(y1)]})
        tp.close()
    except Exception:  # noqa: BLE001 - a broken text layer must not break rendering
        return []
    return lines


def to_bgr(img: Image.Image) -> np.ndarray:
    import cv2

    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def encode_jpeg(arr_or_img, quality: int = 90) -> bytes:
    import cv2

    if isinstance(arr_or_img, Image.Image):
        buf = io.BytesIO()
        arr_or_img.save(buf, "JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    ok, enc = cv2.imencode(".jpg", arr_or_img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise MediaError("encode_failed", "No se pudo codificar la imagen.")
    return enc.tobytes()


def decode_frame(data: bytes, max_side: int = 1280) -> np.ndarray:
    """Fast decode of a camera frame (JPEG/PNG/WEBP) to BGR, bounded size."""
    import cv2

    if sniff(data) not in IMAGE_TYPES:
        raise MediaError("invalid_frame", "El fotograma no es una imagen JPEG/PNG/WEBP.")
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise MediaError("invalid_frame", "No se pudo decodificar el fotograma.")
    h, w = arr.shape[:2]
    if max(h, w) > max_side:
        s = max_side / max(h, w)
        arr = cv2.resize(arr, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    return arr
