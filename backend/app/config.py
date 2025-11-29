"""
Configuration management for the backend application.

Loads environment variables and provides typed configuration objects.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Find the .env file - check backend dir first, then root
_backend_dir = Path(__file__).resolve().parent.parent
_root_dir = _backend_dir.parent
_env_file = _backend_dir / ".env" if (_backend_dir / ".env").exists() else _root_dir / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Security Incident Triage Agent"
    app_version: str = "0.1.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8080

    # Frontend CORS
    frontend_url: str = "http://localhost:3000"

    # Google Cloud / Vertex AI
    google_cloud_project: Optional[str] = None
    google_cloud_location: str = "us-central1"
    vertex_ai_model: str = "gemini-1.5-flash"
    vertex_embedding_model: str = "text-embedding-004"

    # Database (Neon PostgreSQL with pgvector)
    neon_database_url: Optional[str] = None

    # Redis (Upstash)
    upstash_redis_rest_url: Optional[str] = None
    upstash_redis_rest_token: Optional[str] = None

    # Feature flags
    use_stub_llm: bool = True  # Use stub responses when LLM keys are missing
    enable_tracing: bool = True

    model_config = SettingsConfigDict(
        env_file=str(_env_file),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars not defined in Settings
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def is_llm_available() -> bool:
    """Check if LLM credentials are configured."""
    settings = get_settings()
    return settings.google_cloud_project is not None and not settings.use_stub_llm


def is_db_available() -> bool:
    """Check if database is configured."""
    settings = get_settings()
    return settings.neon_database_url is not None


def is_redis_available() -> bool:
    """Check if Redis is configured."""
    settings = get_settings()
    return settings.upstash_redis_rest_url is not None
