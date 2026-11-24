"""BUILD-TIME ONLY: download the OCR ONNX models and verify their SHA-256.

The models are the PaddleOCR PP-OCRv6 / PP-OCRv5 models converted to ONNX and
published by the RapidOCR project (Apache-2.0). They are baked into the image so
the runtime never needs network access. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

BASE = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx"

MODELS = {
    "det_small": ("PP-OCRv6/det/PP-OCRv6_det_small.onnx",
                  "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f"),
    "det_medium": ("PP-OCRv6/det/PP-OCRv6_det_medium.onnx",
                   "92078b7355007ccfffcd4c8cd441a3afd4538904d06881b29a155e1e679907c2"),
    "rec_small": ("PP-OCRv6/rec/PP-OCRv6_rec_small.onnx",
                  "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884"),
    "rec_medium": ("PP-OCRv6/rec/PP-OCRv6_rec_medium.onnx",
                   "eef444829dbbe18d7fea59a3f6eb75647518d2b3a9568d27c92e42940204894b"),
    "rec_latin_v5": ("PP-OCRv5/rec/latin_PP-OCRv5_rec_mobile.onnx",
                     "b20bd37c168a570f583afbc8cd7925603890efbcdc000a59e22c269d160b5f5a"),
    "cls": ("PP-OCRv5/cls/ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx",
            "54379ae5174d026780215fc748a7f31910dee36818e63d49e17dc598ecc82df7"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/models/rapidocr")
    out.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for key, (rel, digest) in MODELS.items():
        target = out / Path(rel).name
        if not target.exists() or sha256(target) != digest:
            url = f"{BASE}/{rel}"
            print(f"downloading {key}: {url}", flush=True)
            with urllib.request.urlopen(url, timeout=300) as resp, target.open("wb") as f:  # noqa: S310 - fixed https URL
                while chunk := resp.read(1 << 20):
                    f.write(chunk)
        got = sha256(target)
        if got != digest:
            target.unlink(missing_ok=True)
            print(f"SHA-256 mismatch for {key}: {got} != {digest}", file=sys.stderr)
            return 1
        manifest[key] = {"file": target.name, "sha256": digest, "source": f"{BASE}/{rel}",
                         "size_bytes": target.stat().st_size}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
