from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("VIE_CONFIGS_DIR", str(Path(__file__).resolve().parents[1] / "configs"))
if not Path(os.environ["VIE_CONFIGS_DIR"]).exists():
    os.environ["VIE_CONFIGS_DIR"] = "/app/configs"

FIXTURES = Path(__file__).parent / "fixtures"


def load_analysis(name: str) -> dict:
    return json.loads((FIXTURES / "ocr" / f"{name}.json").read_text(encoding="utf-8"))


def load_truth(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def analysis():
    return load_analysis


@pytest.fixture
def truth():
    return load_truth
