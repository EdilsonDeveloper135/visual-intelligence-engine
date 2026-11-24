"""Convert vision-engine responses into result models (pure functions)."""

from __future__ import annotations

from ..extraction.normalize import clean_text
from ..extraction.peru import parse_sunat_qr
from ..models.result import Code, Score, TextLine


def lines_from_analysis(page: int, analysis: dict, start: int = 1) -> list[TextLine]:
    out: list[TextLine] = []
    ocr = analysis.get("ocr") or {}
    n = start
    if ocr.get("lines"):
        src = ocr.get("score_source") or ocr.get("engine") or "ocr"
        for ln in ocr["lines"]:
            text = clean_text(ln.get("text"), 1000)
            if not text:
                continue
            out.append(TextLine(id=f"r_{n:04d}", page=page, text=text, bbox=[int(v) for v in ln["bbox"]],
                                polygon=ln.get("polygon"),
                                score=Score(value=float(ln["score"]), source=src) if ln.get("score") is not None
                                else None, source="ocr"))
            n += 1
    elif analysis.get("text_layer"):
        for ln in analysis["text_layer"]:
            text = clean_text(ln.get("text"), 1000)
            if not text:
                continue
            out.append(TextLine(id=f"r_{n:04d}", page=page, text=text, bbox=[int(v) for v in ln["bbox"]],
                                score=None, source="pdf_text"))
            n += 1
    return out


def codes_from_analysis(page: int, analysis: dict, start: int = 1) -> list[dict]:
    out = []
    for i, c in enumerate(analysis.get("codes") or [], start=start):
        text = (c.get("text") or "")[:2000]
        out.append({"id": f"c_{i:02d}", "page": page, "format": c.get("format"), "text": text,
                    "bbox": c.get("bbox"), "source": c.get("source"), "parsed": parse_sunat_qr(text)})
    return out


def code_models(codes: list[dict]) -> list[Code]:
    return [Code(format=c.get("format") or "unknown", text=c["text"], page=c["page"], bbox=c.get("bbox"),
                 parsed=c.get("parsed"), source=c.get("source") or "unknown") for c in codes]
