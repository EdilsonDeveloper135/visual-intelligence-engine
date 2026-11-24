"""Keyframe extraction from UNTRUSTED videos (runs only in the isolated vision container).

1. Sample frames at a fixed rate (default 2 fps), within duration/size limits.
2. Candidate segmentation with a sensitive visual signature (brightness-normalised
   32x32 thumbnail + dHash): any noticeable change opens a candidate scene.
3. Content-aware merge: the sharpest frame of each candidate is OCR'd; consecutive
   candidates with the same text (same document moved / re-framed) are merged.
   Global image descriptors cannot tell two documents with the same layout apart,
   their text can.
"""

from __future__ import annotations

import difflib
import os
import re
import tempfile

import cv2
import numpy as np

from .assess import dhash
from .config import get_settings
from .media import MediaError
from .quality import blur_variance


def _hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _signature(gray: np.ndarray) -> np.ndarray:
    g = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    return (g - g.mean()) / (g.std() + 1e-6)


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^0-9A-Za-zÁÉÍÓÚÑáéíóúñ]+", " ", text)).strip().upper()


def keyframes(data: bytes, sample_fps: float = 2.0, max_keyframes: int = 12, max_side: int = 1600,
              visual_threshold: float = 0.012, hash_threshold: int = 18, text_similarity: float = 0.75) -> dict:
    settings = get_settings()
    fd, path = tempfile.mkstemp(suffix=".video", dir="/tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise MediaError("invalid_video", "No se pudo abrir el video (formato o códec no soportado).")
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if fps <= 0 or fps > 240:
            fps = 25.0
        duration = total / fps if total else 0
        if duration > settings.max_video_seconds:
            raise MediaError("video_too_long",
                             f"El video dura {duration:.0f} s; el máximo es {settings.max_video_seconds} s.")
        step = max(1, round(fps / sample_fps))
        candidates: list[dict] = []
        current: dict | None = None
        idx = sampled = 0
        while True:
            if not cap.grab():
                break
            if idx % step == 0:
                ok, frame = cap.retrieve()
                if not ok or frame is None:
                    break
                sampled += 1
                if sampled > 2000:
                    break
                h, w = frame.shape[:2]
                if max(h, w) > max_side:
                    s = max_side / max(h, w)
                    frame = cv2.resize(frame, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                small = cv2.resize(gray, (640, round(640 * gray.shape[0] / gray.shape[1])), interpolation=cv2.INTER_AREA)
                if small.mean() < 25:
                    idx += 1
                    continue  # too dark to be useful
                sig, hsh, blur = _signature(small), dhash(small), blur_variance(small)
                changed = current is None or float(np.abs(sig - current["sig"]).mean()) >= visual_threshold \
                    or _hamming(hsh, current["dhash"]) >= hash_threshold
                if changed:
                    current = {"sig": sig, "dhash": hsh, "best_blur": -1.0, "frame": None, "t_s": 0.0,
                               "index": idx, "frames": 0}
                    candidates.append(current)
                current["frames"] += 1
                if blur > current["best_blur"]:
                    current.update(best_blur=blur, frame=frame.copy(), t_s=idx / fps, index=idx)
            idx += 1
        cap.release()

        # transitions (a single sampled frame) are dropped when something steadier exists
        steady = [c for c in candidates if c["frames"] >= 2] or candidates
        steady = steady[:40]

        # content-aware merge of consecutive candidates
        from .ocr import get_engine

        engine = get_engine()
        scenes: list[dict] = []
        for c in steady:
            lines, _ = engine.run(c["frame"])
            c["text"] = _norm_text(" ".join(ln.text for ln in lines))
            prev = scenes[-1] if scenes else None
            if prev is not None:
                both_text = len(c["text"]) >= 20 and len(prev["text"]) >= 20
                same_doc = both_text and difflib.SequenceMatcher(None, prev["text"], c["text"]).ratio() >= text_similarity
                both_empty = len(c["text"]) < 20 and len(prev["text"]) < 20 and _hamming(c["dhash"], prev["dhash"]) < hash_threshold
                if same_doc or both_empty:
                    prev["frames"] += c["frames"]
                    if c["best_blur"] > prev["best_blur"]:
                        prev.update(best_blur=c["best_blur"], frame=c["frame"], t_s=c["t_s"], index=c["index"],
                                    text=c["text"])
                    continue
            scenes.append(c)

        # keep scenes with text first, then the sharpest ones
        chosen = sorted(scenes, key=lambda s: (len(s["text"]) < 20, -s["best_blur"]))[:max_keyframes]
        chosen.sort(key=lambda s: s["t_s"])
        out = []
        for s in chosen:
            ok, enc = cv2.imencode(".jpg", s["frame"], [cv2.IMWRITE_JPEG_QUALITY, 92])
            if ok:
                out.append({"t_s": round(s["t_s"], 2), "frame_index": s["index"], "blur_variance": round(s["best_blur"], 1),
                            "dhash": s["dhash"], "scene_frames": s["frames"], "text_chars": len(s["text"]),
                            "jpeg": enc.tobytes()})
        return {"duration_s": round(duration, 2), "fps": round(fps, 2), "frames_total": total, "sampled": sampled,
                "candidate_scenes": len(candidates), "scenes_detected": len(scenes), "keyframes": out}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
