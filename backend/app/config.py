"""Application configuration.

All values can be overridden with environment variables (or a ``.env`` file in
the repository root / backend directory), e.g. ``TRYON_DATABASE_URL=...``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> <repo root>
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRYON_",
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Virtual Try-On API"
    environment: str = "development"
    debug: bool = True

    host: str = "127.0.0.1"
    port: int = 8000

    # SQLite for the MVP. Swap for e.g.
    # postgresql+psycopg://user:pass@localhost:5432/tryon
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'tryon.db'}"

    # Where the clothing catalog lives on disk.
    clothes_dir: Path = REPO_ROOT / "assets" / "clothes"
    # Generated try-on results + thumbnails.
    output_dir: Path = BACKEND_DIR / "data" / "outputs"
    # Phase 2 model weights.
    models_dir: Path = REPO_ROOT / "models"

    # Default try-on engine: "overlay" (Phase 1) | "idm-vton" | "catvton".
    default_engine: str = "overlay"
    cache_enabled: bool = True
    max_upload_mb: int = 12

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @property
    def categories(self) -> list[str]:
        """Folders to create under ``clothes_dir``. Must mirror ``models.Category``,
        which cannot be imported here — models imports database imports config."""
        return ["shirts", "pants", "jackets", "hats", "glasses", "shoes"]

    def ensure_dirs(self) -> None:
        (BACKEND_DIR / "data").mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        for category in self.categories:
            (self.clothes_dir / category).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


settings = get_settings()
