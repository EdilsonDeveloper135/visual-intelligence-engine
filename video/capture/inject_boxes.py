"""Expand <!--OCR_BOXES prefix--> markers into the real OCR boxes of the exported observation."""
import json
import pathlib
import re

root = pathlib.Path(__file__).resolve().parent.parent
data = json.loads((root / "assets/data/factura.json").read_text())
PAD = 4


def boxes(prefix: str) -> str:
    out = [f"<!--OCR_BOXES {prefix}-->"]
    for i, line in enumerate(data["lines"]):
        x0, y0, x1, y1 = line["bbox"]
        out.append(
            f'<div id="{prefix}-ob-{i:02d}" class="ob" style="left: {x0 - PAD}px; top: {y0 - PAD}px; '
            f'width: {x1 - x0 + 2 * PAD}px; height: {y1 - y0 + 2 * PAD}px"></div>'
        )
    out.append(f"<!--/OCR_BOXES {prefix}-->")
    return "\n        ".join(out)


for path in (root / "compositions").glob("*.html"):
    text = path.read_text()
    # idempotent: replace a previously expanded block or a bare marker
    new = re.sub(r"<!--OCR_BOXES (\w+)-->(?:.*?<!--/OCR_BOXES \1-->)?",
                 lambda m: boxes(m.group(1)), text, flags=re.S)
    if new != text:
        path.write_text(new)
        print("boxes injected:", path.name)
