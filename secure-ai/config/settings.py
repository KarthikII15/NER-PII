"""
settings.py — Application configuration via environment variables.
Fails fast on missing API_KEY to prevent running with defaults.
"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings


# For local development, auto-discover .env relative to this file
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    api_key: str  # Required. No default.

    upload_dir: str = "/app/storage/uploads"
    processed_dir: str = "/app/storage/processed"
    signed_dir: str = "/app/storage/signed"
    keys_dir: str = "/app/storage/keys"
    db_path: str = "/app/storage/audit.db"

    max_file_size_mb: int = 50
    processing_timeout_seconds: int = 30

    # NER model control
    use_ner: bool = True  # Set False to use regex-only detection

    class Config:
        env_file = str(_ENV_FILE) if _ENV_FILE.exists() else ".env"
        env_file_encoding = "utf-8"


settings = Settings()
