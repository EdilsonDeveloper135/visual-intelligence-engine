from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIE_", extra="ignore")

    models_dir: Path = Path("/opt/models/rapidocr")
    ocr_model_size: Literal["small", "medium"] = "small"
    # multi_v6 = PP-OCRv6 multilingual (includes Spanish); latin_v5 = PP-OCRv5 Latin-script model
    ocr_rec_variant: Literal["multi_v6", "latin_v5"] = "multi_v6"
    ocr_threads: int = 3
    ocr_text_score: float = 0.5
    # Longest side fed to the text detector (memory grows with the square of it)
    ocr_max_side: int = 1600

    max_upload_mb: int = 100
    max_image_pixels: int = 120_000_000
    work_image_max_side: int = 3000
    max_pdf_pages: int = 30
    pdf_render_dpi: int = 200
    max_video_seconds: int = 600

    # Concurrent heavy analyses (memory bound). Camera assessment is not limited by this.
    max_concurrent_analyses: int = 1
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
