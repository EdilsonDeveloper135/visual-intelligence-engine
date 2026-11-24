"""Anchor a value (typically proposed by the multimodal model) to OCR evidence."""

from __future__ import annotations

import re
from decimal import Decimal

from rapidfuzz import fuzz

from ..models.result import TextLine
from .normalize import digits, parse_date, parse_decimal, strip_accents

NUM_IN_TEXT = re.compile(r"\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})|\d+(?:[.,]\d{1,2})?")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(s).upper()).strip()


def ground(value, typ: str, lines: list[TextLine], limit: int = 3) -> list[TextLine]:
    """Return the OCR lines that contain `value` (empty list if not found)."""
    if value is None or value == "" or not lines:
        return []
    sval = str(value)
    if typ in ("money", "decimal", "integer", "percent"):
        target = parse_decimal(sval)
        if target is None:
            return []
        hits = []
        for ln in lines:
            for m in NUM_IN_TEXT.finditer(ln.text):
                v = parse_decimal(m.group(0))
                if v is not None and v == target and (abs(target) >= Decimal("10") or "." in m.group(0)
                                                      or "," in m.group(0)):
                    hits.append(ln)
                    break
        return hits[:limit]
    if typ == "date":
        target = parse_date(sval) if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", sval) else parse_date(sval)
        if target is None:
            return []
        return [ln for ln in lines if parse_date(ln.text) == target][:limit]
    if typ in ("ruc", "dni", "doc_id"):
        d = digits(sval)
        if len(d) < 8:
            return []
        return [ln for ln in lines if d in digits(ln.text)][:limit]
    if typ == "serie_numero":
        key = re.sub(r"[^A-Z0-9]", "", sval.upper())
        return [ln for ln in lines if key and key in re.sub(r"[^A-Z0-9]", "", ln.text.upper())][:limit]
    if typ == "currency":
        return []  # currencies are usually implicit (symbols); grounding not meaningful
    # free text: fuzzy match (the value may be split across lines)
    target = _norm(sval)
    if len(target) < 2:
        return []
    scored = []
    for ln in lines:
        t = _norm(ln.text)
        if not t:
            continue
        score = fuzz.partial_ratio(target, t) if len(t) >= 3 else 0
        if score >= 88 and min(len(t), len(target)) >= max(3, 0.3 * max(len(t), len(target))):
            scored.append((score, ln))
    scored.sort(key=lambda x: -x[0])
    return [ln for _, ln in scored[:limit]]
