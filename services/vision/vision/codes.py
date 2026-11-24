"""QR codes and barcodes (zxing-cpp, with OpenCV QR fallback)."""

from __future__ import annotations

import cv2
import numpy as np


def _poly_to_bbox(points) -> list[int]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def read_codes(bgr: np.ndarray) -> list[dict]:
    found: dict[str, dict] = {}
    try:
        import zxingcpp

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        for r in zxingcpp.read_barcodes(rgb):
            if not r.valid or not r.text:
                continue
            p = r.position
            pts = [(p.top_left.x, p.top_left.y), (p.top_right.x, p.top_right.y),
                   (p.bottom_right.x, p.bottom_right.y), (p.bottom_left.x, p.bottom_left.y)]
            found.setdefault(r.text, {
                "format": str(r.format).split(".")[-1], "text": r.text,
                "polygon": [[int(x), int(y)] for x, y in pts], "bbox": _poly_to_bbox(pts),
                "source": "zxing-cpp-3.1.1",
            })
    except Exception:  # noqa: BLE001 - fall back to OpenCV
        pass
    if not found:
        try:
            det = cv2.QRCodeDetector()
            text, pts, _ = det.detectAndDecode(bgr)
            if text and pts is not None:
                pts = pts.reshape(-1, 2).tolist()
                found[text] = {"format": "QRCode", "text": text, "polygon": [[int(x), int(y)] for x, y in pts],
                               "bbox": _poly_to_bbox(pts), "source": "opencv-qrcodedetector"}
        except Exception:  # noqa: BLE001
            pass
    return list(found.values())
