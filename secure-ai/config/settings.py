"""
settings.py — Application configuration via environment variables.
Fails fast on missing API_KEY to prevent running with defaults.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    api_key: str  # Required. No default. Will raise ValidationError if missing.

    upload_dir: str = "/app/storage/uploads"
    processed_dir: str = "/app/storage/processed"
    signed_dir: str = "/app/storage/signed"
    keys_dir: str = "/app/storage/keys"
    db_path: str = "/app/storage/audit.db"

    max_file_size_mb: int = 50
    processing_timeout_seconds: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
