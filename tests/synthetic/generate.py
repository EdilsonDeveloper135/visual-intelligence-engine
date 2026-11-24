"""CLI: generate the synthetic sample set (images, PDF, camera video, ground truth).

Usage (inside the tests container):
    python -m synthetic.generate --out /work/examples/generated [--camera] [--pdf]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from . import degrade
from .documents import DocSpec, catalogue, render


def write_sample(out: Path, name: str, img: Image.Image, truth: dict, fmt: str = "png") -> None:
    path = out / f"{name}.{fmt}"
    if fmt == "jpg":
        img.convert("RGB").save(path, "JPEG", quality=92)
    else:
        img.save(path)
    (out / f"{name}.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")


def non_document_scene(w: int = 1280, h: int = 960) -> Image.Image:
    """A desk scene without any document (used to check the model does not invent fields)."""
    img = degrade.to_pil(degrade.desk_background(w, h, seed=11))
    d = ImageDraw.Draw(img)
    d.ellipse((380, 300, 640, 560), fill=(235, 235, 240), outline=(90, 90, 90), width=6)  # cup seen from above
    d.ellipse((440, 360, 580, 500), fill=(70, 40, 20))  # coffee
    d.rounded_rectangle((760, 260, 1060, 760), radius=30, fill=(30, 30, 35))  # phone
    d.rectangle((150, 650, 330, 690), fill=(200, 30, 30))  # pencil
    return img


def write_pdf(out: Path, name: str, spec: DocSpec) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVuB", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    c = canvas.Canvas(str(out / f"{name}.pdf"), pagesize=A4)
    w, h = A4
    y = h - 60
    c.setFont("DejaVuB", 16)
    c.drawString(40, y, spec.issuer_name)
    c.setFont("DejaVuB", 12)
    c.drawRightString(w - 40, y, f"R.U.C. N° {spec.issuer_ruc}")
    y -= 20
    c.drawRightString(w - 40, y, spec.title)
    y -= 20
    c.drawRightString(w - 40, y, f"{spec.serie}-{spec.numero}")
    c.setFont("DejaVu", 11)
    y -= 40
    doc_label = "RUC" if spec.customer_doc_type == "6" else "DNI"
    for line in (f"Fecha de Emisión: {spec.issue_date:%d/%m/%Y}", f"Señor(es): {spec.customer_name}",
                 f"{doc_label}: {spec.customer_doc}", "Moneda: SOLES"):
        c.drawString(40, y, line)
        y -= 18
    y -= 12
    c.setFont("DejaVuB", 11)
    for x, head in ((40, "Cant."), (90, "Unidad"), (150, "Descripción"), (400, "P. Unit."), (480, "Importe")):
        c.drawString(x, y, head)
    c.setFont("DejaVu", 11)
    for it in spec.items:
        y -= 18
        c.drawString(40, y, f"{it.quantity.normalize():f}")
        c.drawString(90, y, it.unit)
        c.drawString(150, y, it.description)
        c.drawRightString(450, y, f"{it.unit_price:,.2f}")
        c.drawRightString(540, y, f"{it.amount:,.2f}")
    y -= 36
    rate = f"{(spec.tax_rate * 100).normalize():f}"
    for label, val in (("Op. Gravada:", spec.taxable), (f"IGV ({rate}%):", spec.tax), ("Importe Total:", spec.total)):
        c.setFont("DejaVuB", 11)
        c.drawString(360, y, label)
        c.drawRightString(540, y, f"S/ {val:,.2f}")
        y -= 18
    c.showPage()
    c.save()
    (out / f"{name}.pdf.json").write_text(json.dumps(spec.ground_truth(), ensure_ascii=False, indent=2), "utf-8")


def write_camera_y4m(out: Path, specs: dict[str, DocSpec], w: int = 960, h: int = 540, fps: int = 5) -> Path:
    """Synthetic webcam stream for Chromium's fake capture device.

    Timeline: empty desk (2 s) -> factura appears (4 s) -> factura moved (2 s) -> boleta (4 s).
    """
    rng = np.random.default_rng(1)
    desk = degrade.desk_background(w, h, seed=21)

    def place(spec_name: str, dx: int = 0) -> np.ndarray:
        doc = render(specs[spec_name])
        scale = (h * 0.92) / doc.height
        doc_small = degrade.to_cv(doc.resize((int(doc.width * scale), int(doc.height * scale))))
        frame = desk.copy()
        y0 = int(h * 0.04)
        x0 = (w - doc_small.shape[1]) // 2 + dx
        frame[y0:y0 + doc_small.shape[0], x0:x0 + doc_small.shape[1]] = doc_small
        return frame

    segments = [(desk, 2), (place("factura_ok"), 4), (place("factura_ok", dx=60), 2), (place("boleta_ok"), 4)]
    path = out / "camera_sequence.y4m"
    with path.open("wb") as f:
        f.write(f"YUV4MPEG2 W{w} H{h} F{fps}:1 Ip A1:1 C420jpeg\n".encode())
        for frame, seconds in segments:
            for _ in range(seconds * fps):
                noisy = np.clip(frame.astype(np.int16) + rng.integers(-3, 4, frame.shape), 0, 255).astype(np.uint8)
                f.write(b"FRAME\n")
                f.write(cv2.cvtColor(noisy, cv2.COLOR_BGR2YUV_I420).tobytes())
    return path


def write_mp4(out: Path, specs: dict[str, DocSpec], w: int = 960, h: int = 540, fps: int = 10) -> Path:
    """Short video with 3 distinct scenes (empty desk, factura, boleta) for the video pipeline."""
    rng = np.random.default_rng(2)
    desk = degrade.desk_background(w, h, seed=31)

    def place(name: str) -> np.ndarray:
        doc = render(specs[name])
        scale = (h * 0.92) / doc.height
        small = degrade.to_cv(doc.resize((int(doc.width * scale), int(doc.height * scale))))
        frame = desk.copy()
        x0 = (w - small.shape[1]) // 2
        frame[int(h * 0.04):int(h * 0.04) + small.shape[0], x0:x0 + small.shape[1]] = small
        return frame

    path = out / "video_documentos.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for frame, seconds in [(desk, 2), (place("factura_ok"), 3), (place("boleta_ok"), 3)]:
        for _ in range(seconds * fps):
            writer.write(np.clip(frame.astype(np.int16) + rng.integers(-2, 3, frame.shape), 0, 255).astype(np.uint8))
    writer.release()
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--camera", action="store_true", help="also write the .y4m fake-camera stream")
    ap.add_argument("--pdf", action="store_true", help="also write a digital PDF")
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    specs = catalogue()
    for name, spec in specs.items():
        write_sample(out, name, render(spec), spec.ground_truth())

    base = render(specs["factura_ok"])
    truth = specs["factura_ok"].ground_truth()
    variants = {
        "factura_rotada_7": degrade.rotate(base, 7),
        "factura_foto_perspectiva": degrade.perspective_photo(base),
        "factura_desenfocada": degrade.blur(base, 11),
        "factura_poca_luz": degrade.low_light(base),
        "factura_ruido_jpeg": degrade.jpeg(degrade.noise(base), 35),
    }
    for name, img in variants.items():
        write_sample(out, name, img, {**truth, "degradation": name}, fmt="jpg")

    blank = Image.new("RGB", (1240, 1754), "white")
    write_sample(out, "pagina_en_blanco", blank, {"document_type_code": None, "blank": True})
    write_sample(out, "escena_sin_documento", non_document_scene(), {"document_type_code": None, "scene": True},
                 fmt="jpg")

    if args.pdf:
        write_pdf(out, "factura_digital", specs["factura_ok"])
    if args.camera:
        write_camera_y4m(out, specs)
        write_mp4(out, specs)
    print(f"generated samples in {out}")


if __name__ == "__main__":
    main()
