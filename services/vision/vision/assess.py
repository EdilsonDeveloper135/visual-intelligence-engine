"""Fast frame assessment for the real-time camera mode (no OCR)."""

from __future__ import annotations

import cv2
import numpy as np

from .preprocess import detect_document_quad
from .quality import blur_variance


def dhash(gray: np.ndarray, size: int = 8) -> str:
    small = cv2.resize(gray, (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    return f"{value:0{size * size // 4}x}"


def assess(bgr: np.ndarray) -> dict:
    h, w = bgr.shape[:2]
    s = 640 / max(h, w)
    small = cv2.resize(bgr, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    quad, ratio = detect_document_quad(small, work_side=640)
    # A frame filled by a sheet has no visible border: treat bright, high-detail frames as "document-like"
    return {
        "width": int(w),
        "height": int(h),
        "dhash": dhash(gray),
        "blur_variance": round(blur_variance(gray), 1),
        "brightness": round(float(gray.mean()), 1),
        "contrast": round(float(gray.std()), 1),
        "document_quad": (quad / s).round().astype(int).tolist() if quad is not None else None,
        "document_area_ratio": round(ratio, 3),
    }
