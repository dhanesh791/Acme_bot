from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    data_dir: Path = PROJECT_ROOT / "data"
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "256"))
    retrieval_top_k: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
    min_retrieval_score: float = float(os.getenv("MIN_RETRIEVAL_SCORE", "0.12"))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
    chunk_rows: int = int(os.getenv("CHUNK_ROWS", "6"))
    chunk_max_chars: int = int(os.getenv("CHUNK_MAX_CHARS", "2200"))
    embedding_batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))
    embedding_max_retries: int = int(os.getenv("EMBEDDING_MAX_RETRIES", "3"))
    retrieval_candidate_multiplier: int = int(os.getenv("RETRIEVAL_CANDIDATE_MULTIPLIER", "3"))
    max_chunks_per_source: int = int(os.getenv("MAX_CHUNKS_PER_SOURCE", "2"))
    session_retention_hours: int = int(os.getenv("SESSION_RETENTION_HOURS", "24"))

    @property
    def index_path(self) -> Path:
        return self.data_dir / "lance"

    @property
    def openai_api_key(self) -> str | None:
        return os.getenv("OPENAI_API_KEY")

    @property
    def openai_embedding_model(self) -> str:
        return os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    @property
    def openai_chat_model(self) -> str:
        return os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")


settings = Settings()
