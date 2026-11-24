"""Scene-change logic for the real-time camera mode (pure, deterministic, testable).

Each frame arrives with a fast assessment from the vision engine (64-bit dHash,
sharpness, brightness, detected document quad). The tracker decides:

  repeated    : same scene as the current observation -> not analysed again
  stabilizing : the scene changed, waiting for it to be stable
  new         : a stable new scene -> analyse the sharpest frame of the window
  updated     : same scene but clearly better quality, or a moderate change
                (e.g. document moved) -> new observation that supersedes the old
  ignored     : unusable frame (too dark / too blurry)
  throttled   : analysis would exceed the configured rate
  busy        : the previous camera observation is still being processed
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def signature_distance(a: str | None, b: str | None) -> float | None:
    """Mean absolute difference of two brightness-normalised 32x32 signatures (None if unavailable)."""
    if not a or not b:
        return None
    va, vb = base64.b64decode(a), base64.b64decode(b)
    if len(va) != len(vb) or not va:
        return None
    total = sum(abs((x if x < 128 else x - 256) - (y if y < 128 else y - 256)) for x, y in zip(va, vb))
    return total / len(va) / 25.0


@dataclass
class Scene:
    dhash: str
    signature: str | None
    best_blur: float
    has_document: bool
    observation_id: str | None = None
    analysed_at: float = 0.0
    last_seen: float = 0.0
    repeats: int = 0


@dataclass
class Decision:
    action: str
    reason: str
    distance: int | None = None
    best_index: int | None = None  # index in the stabilisation window of the frame to analyse
    document_appeared: bool = False


@dataclass
class SceneTracker:
    repeat_threshold: int = 6
    new_threshold: int = 18
    stable_frames: int = 2
    min_brightness: float = 25.0
    min_blur: float = 15.0
    quality_gain: float = 1.6
    min_interval_s: float = 3.0
    # content-change threshold on the normalised layout signature (same scene + noise ~0.004,
    # lighting change ~0.008, different document with the same layout ~0.016)
    visual_threshold: float = 0.012
    current: Scene | None = None
    window: list[dict] = field(default_factory=list)
    last_analysis_at: float = -1e9

    def _stable(self) -> bool:
        if len(self.window) < self.stable_frames:
            return False
        last = self.window[-self.stable_frames:]
        for i in range(len(last) - 1):
            if hamming(last[i]["dhash"], last[i + 1]["dhash"]) > self.repeat_threshold:
                return False
            sd = signature_distance(last[i].get("signature"), last[i + 1].get("signature"))
            if sd is not None and sd >= self.visual_threshold:
                return False
        return True

    def _best(self) -> int:
        start = max(0, len(self.window) - self.stable_frames)
        idx = max(range(start, len(self.window)), key=lambda i: self.window[i]["blur_variance"])
        return idx

    def decide(self, a: dict, now: float, can_commit: bool = True) -> Decision:
        self._can_commit = can_commit
        if a["brightness"] < self.min_brightness or a["blur_variance"] < self.min_blur:
            return Decision("ignored", "Fotograma demasiado oscuro o borroso.")
        has_doc = a.get("document_quad") is not None
        if self.current is None:
            self.window.append(a)
            self.window = self.window[-8:]
            if not self._stable():
                return Decision("stabilizing", "Esperando una escena estable.")
            return self._commit("new", "Primera escena estable.", now, None, has_doc, appeared=has_doc)

        d = hamming(a["dhash"], self.current.dhash)
        sd = signature_distance(a.get("signature"), self.current.signature)
        same_content = sd is None or sd < self.visual_threshold
        if d <= self.repeat_threshold and same_content:
            self.window.clear()
            self.current.last_seen = now
            self.current.repeats += 1
            better = a["blur_variance"] > self.current.best_blur * self.quality_gain
            if better and now - self.current.analysed_at >= self.min_interval_s * 3:
                self.window.append(a)
                return self._commit("updated", "Misma escena con calidad claramente mejor.", now, d, has_doc)
            return Decision("repeated", "Escena prácticamente idéntica a la ya analizada.", d)

        self.window.append(a)
        self.window = self.window[-8:]
        if not self._stable():
            return Decision("stabilizing", "La escena cambió; esperando estabilidad.", d)
        kind = "new" if d >= self.new_threshold else "updated"
        reason = ("Escena nueva." if kind == "new" else
                  "Cambio de contenido o de encuadre; la lectura del texto decidirá si es otro documento.")
        appeared = has_doc and not self.current.has_document
        return self._commit(kind, reason, now, d, has_doc, appeared=appeared)

    def _commit(self, kind: str, reason: str, now: float, d: int | None, has_doc: bool,
                appeared: bool = False) -> Decision:
        if not getattr(self, "_can_commit", True):
            return Decision("busy", "Análisis anterior en curso; se reintentará con el siguiente fotograma.", d)
        if now - self.last_analysis_at < self.min_interval_s:
            return Decision("throttled", "Límite de frecuencia de análisis alcanzado.", d)
        best = self._best() if self.window else None
        frame = self.window[best] if best is not None else None
        self.current = Scene(dhash=(frame or {"dhash": self.current.dhash if self.current else "0"})["dhash"],
                             signature=(frame or {}).get("signature"),
                             best_blur=(frame or {}).get("blur_variance", 0.0), has_document=has_doc,
                             analysed_at=now, last_seen=now)
        self.last_analysis_at = now
        decision = Decision(kind, reason, d, best_index=best, document_appeared=appeared)
        return decision

    def bind_observation(self, observation_id: str) -> None:
        if self.current is not None:
            self.current.observation_id = observation_id
