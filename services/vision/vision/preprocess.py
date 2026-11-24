"""Document preprocessing with OpenCV. The original image is never modified:
every function returns a new array plus a description of what was applied.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class Preprocessed:
    image: np.ndarray  # BGR
    steps: list[dict] = field(default_factory=list)
    # 3x3 matrix mapping work-image coordinates -> processed-image coordinates
    transform: list[list[float]] = field(default_factory=lambda: np.eye(3).tolist())
    document_quad: list[list[int]] | None = None
    skew_angle: float = 0.0

    @property
    def changed(self) -> bool:
        return any(s.get("applied") for s in self.steps)


def _order_quad(pts: np.ndarray) -> np.ndarray:
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def detect_document_quad(bgr: np.ndarray, work_side: int = 800) -> tuple[np.ndarray | None, float]:
    """Find the largest convex quadrilateral (a sheet of paper). Returns (quad, area_ratio)."""
    h, w = bgr.shape[:2]
    s = work_side / max(h, w)
    small = cv2.resize(bgr, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    candidates = []
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    candidates.append(edges)
    # Bright paper on a darker background
    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    candidates.append(cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)))
    best, best_area = None, 0.0
    img_area = small.shape[0] * small.shape[1]
    for mask in candidates:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
            area = cv2.contourArea(c)
            if area < 0.15 * img_area:
                break
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx) and area > best_area:
                best, best_area = approx, area
    if best is None:
        return None, 0.0
    return _order_quad(best) / s, float(best_area / img_area)


def warp_document(bgr: np.ndarray, quad: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tl, tr, br, bl = quad
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)
    m = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    return cv2.warpPerspective(bgr, m, (width, height), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE), m


def estimate_skew(gray: np.ndarray) -> float:
    """Skew angle (degrees, counter-clockwise positive) from text line orientation."""
    h, w = gray.shape[:2]
    s = 1200 / max(h, w)
    small = cv2.resize(gray, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)
    binary = cv2.adaptiveThreshold(small, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)
    # join characters into line blobs
    joined = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3)))
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    angles, weights = [], []
    for c in contours:
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(c)
        if rw < rh:
            rw, rh = rh, rw
            ang = ang - 90
        if rw < 60 or rh < 4 or rw / max(rh, 1) < 4:
            continue
        # OpenCV versions differ in their minAreaRect angle convention: fold into (-45, 45]
        while ang <= -45:
            ang += 90
        while ang > 45:
            ang -= 90
        angles.append(ang)
        weights.append(rw)
    if len(angles) < 3:
        return 0.0
    angles = np.array(angles)
    weights = np.array(weights)
    med = np.median(angles)
    keep = np.abs(angles - med) < 3
    if keep.sum() < 3:
        return 0.0
    return float(-np.average(angles[keep], weights=weights[keep]))


def rotate(bgr: np.ndarray, angle: float) -> tuple[np.ndarray, np.ndarray]:
    h, w = bgr.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    out = cv2.warpAffine(bgr, m, (nw, nh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
                         borderValue=(255, 255, 255))
    return out, np.vstack([m, [0, 0, 1]])


def normalize_illumination(bgr: np.ndarray) -> np.ndarray:
    """Divide by a blurred background estimate: removes shadows and gradients."""
    out = []
    for ch in cv2.split(bgr):
        bg = cv2.medianBlur(cv2.dilate(ch, np.ones((7, 7), np.uint8)), 31)
        norm = cv2.divide(ch, bg, scale=255)
        out.append(norm)
    return cv2.merge(out)


def clahe(bgr: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l_ch, a, b = cv2.split(lab)
    l_ch = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l_ch)
    return cv2.cvtColor(cv2.merge([l_ch, a, b]), cv2.COLOR_LAB2BGR)


def denoise(bgr: np.ndarray) -> np.ndarray:
    return cv2.bilateralFilter(bgr, 7, 50, 50)


def preprocess(bgr: np.ndarray, quality_flags: list[str]) -> Preprocessed:
    """Apply only the steps the image needs. Returns a NEW image."""
    img = bgr
    total = np.eye(3)
    steps: list[dict] = []
    h, w = img.shape[:2]

    quad, ratio = detect_document_quad(img)
    doc_quad = quad.round().astype(int).tolist() if quad is not None else None
    # Warp only when the sheet does not already fill the frame (photos, not scans)
    if quad is not None and ratio < 0.85:
        img, m = warp_document(img, quad)
        total = m @ total
        steps.append({"name": "perspective_correction", "applied": True, "area_ratio": round(ratio, 3)})
    else:
        steps.append({"name": "perspective_correction", "applied": False,
                      "reason": "no_document_border" if quad is None else "document_fills_frame"})

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    angle = estimate_skew(gray)
    if 0.3 <= abs(angle) <= 20:
        img, m = rotate(img, -angle)
        total = m @ total
        steps.append({"name": "deskew", "applied": True, "angle_deg": round(angle, 2)})
    else:
        steps.append({"name": "deskew", "applied": False, "angle_deg": round(angle, 2)})

    if "too_dark" in quality_flags or "low_contrast" in quality_flags:
        img = normalize_illumination(img)
        img = clahe(img)
        steps.append({"name": "illumination_and_contrast", "applied": True})
    if "noisy" in quality_flags:
        img = denoise(img)
        steps.append({"name": "denoise", "applied": True, "method": "bilateral"})

    return Preprocessed(image=img, steps=steps, transform=total.tolist(), document_quad=doc_quad,
                        skew_angle=round(angle, 2))
