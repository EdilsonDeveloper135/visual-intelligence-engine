"""Photometric / geometric degradations that imitate phone photos of documents."""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image


def to_cv(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def to_pil(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))


def desk_background(w: int, h: int, seed: int = 3) -> np.ndarray:
    """Wood-like textured background (no external assets)."""
    rng = np.random.default_rng(seed)
    base = np.zeros((h, w, 3), np.float32)
    base[:] = (60, 95, 140)  # brownish in BGR
    stripes = (np.sin(np.linspace(0, 40, w))[None, :] * 12).astype(np.float32)
    noise = rng.normal(0, 8, (h, w)).astype(np.float32)
    for c in range(3):
        base[:, :, c] += stripes + noise
    return np.clip(base, 0, 255).astype(np.uint8)


def rotate(img: Image.Image, angle: float) -> Image.Image:
    return img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor="white")


def perspective_photo(img: Image.Image, out_w: int = 1600, out_h: int = 1200, seed: int = 3,
                      doc_scale: float = 0.62) -> Image.Image:
    """Place the document on a desk with a perspective warp (as photographed)."""
    src = to_cv(img)
    h, w = src.shape[:2]
    bg = desk_background(out_w, out_h, seed)
    dh = out_h * doc_scale * 1.25
    dw = dh * w / h
    cx, cy = out_w / 2, out_h / 2
    dst = np.float32([
        [cx - dw / 2 + 40, cy - dh / 2 + 10],
        [cx + dw / 2 - 10, cy - dh / 2 + 45],
        [cx + dw / 2 + 25, cy + dh / 2 - 5],
        [cx - dw / 2 - 20, cy + dh / 2 - 30],
    ])
    m = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), dst)
    warped = cv2.warpPerspective(src, m, (out_w, out_h))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (out_w, out_h))
    out = bg.copy()
    out[mask > 0] = warped[mask > 0]
    # soft shadow / vignette
    yy, xx = np.mgrid[0:out_h, 0:out_w]
    vignette = 1 - 0.25 * (((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    out = np.clip(out.astype(np.float32) * vignette[..., None], 0, 255).astype(np.uint8)
    return to_pil(out)


def blur(img: Image.Image, ksize: int = 9) -> Image.Image:
    return to_pil(cv2.GaussianBlur(to_cv(img), (ksize, ksize), 0))


def low_light(img: Image.Image, gamma: float = 2.2, gain: float = 0.55) -> Image.Image:
    arr = to_cv(img).astype(np.float32) / 255.0
    arr = np.power(arr, gamma) * gain
    # uneven illumination gradient
    h, w = arr.shape[:2]
    grad = np.linspace(1.0, 0.55, w)[None, :, None]
    return to_pil(np.clip(arr * grad * 255, 0, 255).astype(np.uint8))


def noise(img: Image.Image, sigma: float = 18, seed: int = 5) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = to_cv(img).astype(np.float32)
    arr += rng.normal(0, sigma, arr.shape)
    return to_pil(np.clip(arr, 0, 255).astype(np.uint8))


def jpeg(img: Image.Image, quality: int = 35) -> Image.Image:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")
