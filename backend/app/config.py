from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_DIR / ".env", extra="ignore")

    app_host: str = "127.0.0.1"
    app_port: int = 8765
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    allowed_hosts: str = "127.0.0.1,localhost"
    data_dir: Path = PROJECT_DIR / "data"
    upload_dir: Path = PROJECT_DIR / "uploads"
    model_base_url: str = "https://api.openai.com/v1"
    model_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    encryption_key: str = ""
    schedule_timezone: str = "Asia/Shanghai"
    min_publish_interval_seconds: int = 90
    max_retries: int = 1
    retry_delay_seconds: int = 120
    ffmpeg_bin: str = ""
    ffprobe_bin: str = ""
    max_video_upload_mb: int = Field(default=4096, ge=1, le=100_000)
    max_video_duration_seconds: int = Field(default=14_400, ge=1, le=86_400)
    video_transcode_timeout_seconds: int = Field(default=1800, ge=60, le=86_400)
    video_upload_timeout_seconds: int = Field(default=1800, ge=60, le=86_400)
    image_base_url: str = ""
    image_api_key: str = ""
    image_model: str = ""
    compliance_enabled: bool = True
    compliance_ruleset_version: str = "2026-11-26"
    publishing_enabled: bool = True

    @field_validator("data_dir", "upload_dir", mode="after")
    @classmethod
    def resolve_project_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_DIR / value

    @property
    def video_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def asset_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def cors_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_host_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "covers").mkdir(parents=True, exist_ok=True)
    settings.video_dir.mkdir(parents=True, exist_ok=True)
    settings.asset_dir.mkdir(parents=True, exist_ok=True)
    return settings
