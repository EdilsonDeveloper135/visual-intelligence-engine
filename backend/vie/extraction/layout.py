"""Group OCR/PDF text lines into visual rows (reading order)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models.result import TextLine


@dataclass
class Row:
    page: int
    lines: list[TextLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(ln.text for ln in self.lines)

    @property
    def ids(self) -> list[str]:
        return [ln.id for ln in self.lines]

    @property
    def bbox(self) -> list[int]:
        return union_bbox([ln.bbox for ln in self.lines])

    @property
    def y_center(self) -> float:
        b = self.bbox
        return (b[1] + b[3]) / 2


def union_bbox(boxes: list[list[int]]) -> list[int]:
    if not boxes:
        return [0, 0, 0, 0]
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def build_rows(lines: list[TextLine]) -> list[Row]:
    """Rows ordered by page, then top-to-bottom; lines inside a row ordered left-to-right."""
    rows: list[Row] = []
    by_page: dict[int, list[TextLine]] = {}
    for ln in lines:
        by_page.setdefault(ln.page, []).append(ln)
    for page in sorted(by_page):
        page_rows: list[Row] = []
        for ln in sorted(by_page[page], key=lambda x: (x.bbox[1] + x.bbox[3]) / 2):
            cy = (ln.bbox[1] + ln.bbox[3]) / 2
            h = max(1, ln.bbox[3] - ln.bbox[1])
            target = None
            for row in page_rows:
                rb = row.bbox
                rh = max(1, rb[3] - rb[1])
                if abs(cy - (rb[1] + rb[3]) / 2) < 0.5 * min(h, rh):
                    target = row
                    break
            if target is None:
                page_rows.append(Row(page=page, lines=[ln]))
            else:
                target.lines.append(ln)
        for row in page_rows:
            row.lines.sort(key=lambda x: x.bbox[0])
        page_rows.sort(key=lambda r: r.bbox[1])
        rows.extend(page_rows)
    return rows
