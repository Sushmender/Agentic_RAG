"""
backend/app/core/config.py
Pydantic Settings configuration for the Multimodal RAG backend.
All values loaded from environment / .env file.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import AnyUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "Multimodal RAG API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── CORS ─────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # ── Auth (JWT) ───────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = Field(default="dev-secret-key-change-in-prod", description="Secret key for JWT signing")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── LandingAI ADE ────────────────────────────────────────────────────────
    LANDINGAI_API_KEY: str = Field(default="", description="LandingAI ADE API key")
    LANDINGAI_API_URL: str = "https://api.landing.ai/v1/tools/document-analysis"
    ADE_TIER: str = "verity"  # always DPT-3 Verity (cost-optimized)

    # ── OpenRouter ───────────────────────────────────────────────────────────
    OPENROUTER_API_KEY: str = Field(default="", description="OpenRouter API key")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    EMBEDDING_MODEL: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    RERANKER_MODEL: str = "nvidia/llama-nemotron-rerank-vl-1b-v2:free"
    FALLBACK_LLM_MODEL: str = "nvidia/nemotron-3-super-120b-a12b:free"

    # ── Groq (Primary LLM) ───────────────────────────────────────────────────
    GROQ_API_KEY: str = Field(default="", description="Groq API key")
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    PRIMARY_LLM_MODEL: str = "qwen/qwen3.8-27b"
    SECONDARY_LLM_MODEL: str = "nvidia/nemotron-3-super-120b-a12b:free"

    # ── Redis (Upstash) ──────────────────────────────────────────────────────
    REDIS_URL: str = Field(default="redis://localhost:6379", description="Redis connection URL (rediss:// for Upstash TLS)")

    # ── ChromaDB ─────────────────────────────────────────────────────────────
    CHROMA_DB_PATH: str = "./data/chroma_db"
    CHROMA_COLLECTION_NAME: str = "ade_documents"

    # ── Storage paths ─────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "./data/uploads"
    ADE_OUTPUT_DIR: str = "./data/ade_outputs"

    # ── RAG pipeline ─────────────────────────────────────────────────────────
    RETRIEVAL_TOP_N: int = 20
    RERANK_TOP_K: int = 5
    MAX_CONTEXT_TOKENS: int = 8000
    EMBEDDING_BATCH_SIZE: int = 16

    # ── Upload limits ─────────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 50

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    # ── Resilience ───────────────────────────────────────────────────────────
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_WAIT_SECONDS: float = 1.0
    TIMEOUT_SECONDS: float = 30.0

    # ── Allowed MIME types ───────────────────────────────────────────────────
    ALLOWED_MIME_TYPES: List[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/msword",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/tiff",
    ]

    def get_upload_dir(self) -> Path:
        path = Path(self.UPLOAD_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_ade_output_dir(self) -> Path:
        path = Path(self.ADE_OUTPUT_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_chroma_db_path(self) -> Path:
        path = Path(self.CHROMA_DB_PATH)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton — instantiated once per process."""
    return Settings()
