"""Image quality measurements (heuristic, NOT probabilities).

Every metric is reported with its raw value; flags use fixed, documented
thresholds calibrated on the synthetic test set.
"""

from __future__ import annotations

import cv2
import numpy as np

THRESHOLDS = {
    "blur_variance_min": 120.0,  # variance of Laplacian on a 1000 px image
    "brightness_min": 70.0,
    "brightness_max": 235.0,
    "contrast_min": 35.0,
    "noise_sigma_max": 12.0,
    "min_side_px": 600,
}


def _normalized_gray(bgr: np.ndarray, target: int = 1000) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    h, w = gray.shape[:2]
    s = target / max(h, w)
    if abs(s - 1.0) > 0.05:
        gray = cv2.resize(gray, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)
    return gray


def blur_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def noise_sigma(gray: np.ndarray) -> float:
    """Immerkaer fast noise estimation."""
    kernel = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float64)
    h, w = gray.shape[:2]
    conv = cv2.filter2D(gray.astype(np.float64), -1, kernel)
    return float(np.sum(np.abs(conv)) * np.sqrt(0.5 * np.pi) / (6.0 * (w - 2) * (h - 2)))


def measure(bgr: np.ndarray) -> dict:
    h, w = bgr.shape[:2]
    gray = _normalized_gray(bgr)
    metrics = {
        "width": int(w),
        "height": int(h),
        "megapixels": round(w * h / 1e6, 2),
        "blur_variance": round(blur_variance(gray), 1),
        "brightness": round(float(gray.mean()), 1),
        "contrast": round(float(gray.std()), 1),
        "noise_sigma": round(noise_sigma(gray), 2),
    }
    t = THRESHOLDS
    flags = []
    if metrics["blur_variance"] < t["blur_variance_min"]:
        flags.append("blurry")
    if metrics["brightness"] < t["brightness_min"]:
        flags.append("too_dark")
    if metrics["brightness"] > t["brightness_max"] and metrics["contrast"] < t["contrast_min"]:
        flags.append("overexposed")
    if metrics["contrast"] < t["contrast_min"]:
        flags.append("low_contrast")
    if metrics["noise_sigma"] > t["noise_sigma_max"]:
        flags.append("noisy")
    if min(w, h) < t["min_side_px"]:
        flags.append("low_resolution")
    serious = {"blurry", "too_dark", "low_resolution"}
    level = "good" if not flags else ("poor" if serious & set(flags) else "fair")
    return {"metrics": metrics, "flags": flags, "level": level, "thresholds": t,
            "method": "heuristic (OpenCV); not a probability"}
