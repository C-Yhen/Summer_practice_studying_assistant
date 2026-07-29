from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "StudyPilot API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./backend/studypilot.db"
    jwt_secret: str = "development-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    auto_create_tables: bool = True
    sync_document_processing: bool = True
    upload_dir: Path = Path("./backend/storage/uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    pdf_ocr_enabled: bool = True
    pdf_ocr_language: str = "chi_sim+eng"
    pdf_ocr_dpi: int = 300
    pdf_ocr_min_text_chars: int = 80
    rag_top_k: int = 5
    embedding_dimension: int = 1024
    llm_provider: str = "mock"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_chat_model: str = ""
    llm_embedding_model: str = ""
    llm_embedding_batch_size: int = 20
    # Interactive course Q&A may need more time than compact structured jobs.
    rag_chat_timeout_seconds: int = 60
    # Remote AI is optional enhancement work. These bounds protect a worker from
    # a slow provider; interactive endpoints never wait for them.
    ai_recommend_timeout_seconds: int = 12
    ai_plan_timeout_seconds: int = 18
    ai_practice_timeout_seconds: int = 18
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        # SQLAlchemy 2 + psycopg 3. Hosted platforms often expose the legacy form.
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @field_validator("embedding_dimension")
    @classmethod
    def require_supported_embedding_dimension(cls, value: int) -> int:
        # The PostgreSQL pgvector column is Vector(1024). Keep runtime
        # configuration aligned with that persisted schema.
        if value != 1024:
            raise ValueError("EMBEDDING_DIMENSION must be 1024 for the current database schema")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
