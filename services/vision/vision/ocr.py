"""OCR with RapidOCR (onnxruntime) using PaddleOCR PP-OCRv6 / PP-OCRv5 ONNX models.

Models are loaded from local files baked into the image (no download at runtime).
Scores returned are the recognizer's own per-line confidence, tagged with their
origin; they are NOT calibrated probabilities.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np

from .config import get_settings

_lock = threading.Lock()

try:  # onnxruntime ships optional telemetry (1DS); disable it explicitly (privacy by default)
    import onnxruntime as _ort

    _ort.disable_telemetry_events()
except Exception:  # noqa: BLE001
    pass
_engines: dict[tuple, "OcrEngine"] = {}


@dataclass
class OcrLine:
    text: str
    polygon: list[list[int]]
    bbox: list[int]
    score: float


class OcrEngine:
    def __init__(self, size: str, rec_variant: str, threads: int):
        from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion, RapidOCR

        s = get_settings()
        d = s.models_dir
        det_path = d / f"PP-OCRv6_det_{size}.onnx"
        if rec_variant == "latin_v5":
            rec_path, rec_version, rec_lang, rec_type = (
                d / "latin_PP-OCRv5_rec_mobile.onnx", OCRVersion.PPOCRV5, LangRec.LATIN, ModelType.MOBILE)
            self.rec_name = "latin_PP-OCRv5_rec_mobile"
        else:
            rec_path, rec_version, rec_lang, rec_type = (
                d / f"PP-OCRv6_rec_{size}.onnx", OCRVersion.PPOCRV6, "multi",
                ModelType.SMALL if size == "small" else ModelType.MEDIUM)
            self.rec_name = f"PP-OCRv6_rec_{size}"
        self.det_name = f"PP-OCRv6_det_{size}"
        params = {
            "Global.log_level": "warning",
            "Global.text_score": s.ocr_text_score,
            "Global.use_cls": True,
            "Global.max_side_len": s.ocr_max_side,
            "Det.engine_type": EngineType.ONNXRUNTIME,
            "Det.ocr_version": OCRVersion.PPOCRV6,
            "Det.lang_type": LangDet.MULTI,
            "Det.model_type": ModelType.SMALL if size == "small" else ModelType.MEDIUM,
            "Det.model_path": str(det_path),
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Rec.ocr_version": rec_version,
            "Rec.lang_type": rec_lang,
            "Rec.model_type": rec_type,
            "Rec.model_path": str(rec_path),
            "Cls.engine_type": EngineType.ONNXRUNTIME,
            "Cls.model_path": str(d / "ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx"),
            "Cls.ocr_version": OCRVersion.PPOCRV5,
            "Cls.cls_image_shape": [3, 80, 160],  # PP-LCNet textline orientation model input
            "EngineConfig.onnxruntime.intra_op_num_threads": threads,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        }
        self._ocr = RapidOCR(params=params)
        self.engine_id = f"rapidocr-3.10.0:{self.det_name}+{self.rec_name}"

    def run(self, bgr: np.ndarray) -> tuple[list[OcrLine], float]:
        t0 = time.perf_counter()
        result = self._ocr(bgr)
        elapsed = time.perf_counter() - t0
        lines: list[OcrLine] = []
        if result is None or result.boxes is None or result.txts is None:
            return lines, elapsed
        for box, txt, score in zip(result.boxes, result.txts, result.scores):
            poly = np.asarray(box).round().astype(int)
            xs, ys = poly[:, 0], poly[:, 1]
            text = str(txt).strip()
            if not text:
                continue
            lines.append(OcrLine(text=text, polygon=poly.tolist(),
                                 bbox=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                                 score=round(float(score), 4)))
        return lines, elapsed


def get_engine(size: str | None = None, rec_variant: str | None = None) -> OcrEngine:
    s = get_settings()
    key = (size or s.ocr_model_size, rec_variant or s.ocr_rec_variant, s.ocr_threads)
    with _lock:
        if key not in _engines:
            _engines[key] = OcrEngine(*key)
        return _engines[key]


def reading_order(lines: list[OcrLine]) -> list[list[int]]:
    """Group line indices into visual rows (top->bottom, left->right)."""
    if not lines:
        return []
    order = sorted(range(len(lines)), key=lambda i: (lines[i].bbox[1] + lines[i].bbox[3]) / 2)
    rows: list[list[int]] = []
    for i in order:
        y0, y1 = lines[i].bbox[1], lines[i].bbox[3]
        cy, hgt = (y0 + y1) / 2, max(1, y1 - y0)
        placed = False
        for row in rows:
            r = lines[row[0]]
            ry0, ry1 = r.bbox[1], r.bbox[3]
            if abs(cy - (ry0 + ry1) / 2) < 0.5 * min(hgt, max(1, ry1 - ry0)):
                row.append(i)
                placed = True
                break
        if not placed:
            rows.append([i])
    for row in rows:
        row.sort(key=lambda i: lines[i].bbox[0])
    rows.sort(key=lambda row: min(lines[i].bbox[1] for i in row))
    return rows
