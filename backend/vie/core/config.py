"""Runtime configuration (environment variables, see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIE_", extra="ignore")

    # --- service wiring -------------------------------------------------------
    database_url: SecretStr = SecretStr("postgresql+asyncpg://vie:vie@postgres:5432/vie")
    vision_url: str = "http://vision:8000"
    ollama_url: str = "http://ollama:11434"
    data_dir: Path = Path("/data")
    configs_dir: Path = Path("/app/configs")

    # --- security ----------------------------------------------------------------
    secret_key: SecretStr = SecretStr("dev-insecure-secret-change-me")
    access_key: SecretStr = SecretStr("dev-access-key")
    auth_enabled: bool = True
    port: int = 8080
    allowed_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost"])
    session_hours: int = 12
    cookie_name: str = "vie_session"

    # --- multimodal model ----------------------------------------------------------
    vlm_model: str = "qwen3-vl:2b-instruct"
    vlm_num_ctx: int = 4096
    vlm_num_predict: int = 768
    vlm_num_thread: int = 6
    vlm_max_side_document: int = 1280
    vlm_max_side_camera: int = 1024
    vlm_max_ocr_chars: int = 2500
    vlm_timeout_s: int = 300
    vlm_temperature: float = 0.0
    vlm_seed: int = 42
    vlm_enabled: bool = True

    # --- limits --------------------------------------------------------------------
    max_image_mb: int = 20
    max_pdf_mb: int = 30
    max_pdf_pages: int = 30
    max_files_per_request: int = 10
    job_timeout_s: int = 600
    storage_quota_gb: float = 10.0
    retention_days: int = 0

    # --- camera ----------------------------------------------------------------------
    camera_min_ocr_interval_s: float = 3.0
    camera_min_vlm_interval_s: float = 60.0
    camera_auto_vlm: bool = False

    log_level: str = "INFO"

    @property
    def allowed_origins(self) -> set[str]:
        return {f"http://{h}:{self.port}" for h in self.allowed_hosts}


@lru_cache
def get_settings() -> Settings:
    return Settings()
