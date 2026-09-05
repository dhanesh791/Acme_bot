from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Shared by every local ONNX model loader (embeddings, reranker, local LLM generation).
# A fixed, stable location under data/ rather than fastembed's own default of the OS
# temp directory, which Windows or a cleanup tool can silently clear (see ISSUES.md).
MODEL_CACHE_DIR = str(PROJECT_ROOT / "data" / "model_cache")


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
    session_retention_hours: int = int(os.getenv("SESSION_RETENTION_HOURS", "24"))
    # "auto" = OpenAI when a key is configured, else the local FastEmbed model. "hash" and
    # "local" force a specific provider regardless of key presence (tests use "hash" for speed).
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "auto")
    local_embedding_model: str = os.getenv("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    use_reranker: bool = os.getenv("USE_RERANKER", "true").strip().lower() not in ("0", "false", "no")
    reranker_model: str = os.getenv("RERANKER_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
    rerank_candidate_pool: int = int(os.getenv("RERANK_CANDIDATE_POOL", "20"))
    min_rerank_score: float = float(os.getenv("MIN_RERANK_SCORE", "-11.0"))
    rrf_k: int = int(os.getenv("RRF_K", "60"))
    mmr_lambda: float = float(os.getenv("MMR_LAMBDA", "0.65"))
    # "auto" = OpenAI when a key is configured, else the extractive fallback (unchanged
    # default). Unlike embedding_provider, "auto" does NOT fall through to the local LLM -
    # even the smallest well-supported option is a ~2.8GB download with much higher
    # per-answer latency than either OpenAI or the instant extractive fallback, so it
    # needs an explicit opt-in ("local") rather than being silently auto-selected.
    # "openai" forces OpenAI (errors without a key); "none" forces the extractive
    # fallback even when a key is configured.
    generation_provider: str = os.getenv("GENERATION_PROVIDER", "auto")
    local_llm_model_repo: str = os.getenv("LOCAL_LLM_MODEL_REPO", "microsoft/Phi-3.5-mini-instruct-onnx")
    local_llm_model_variant: str = os.getenv("LOCAL_LLM_MODEL_VARIANT", "cpu_and_mobile/cpu-int4-awq-block-128-acc-level-4")
    local_llm_max_new_tokens: int = int(os.getenv("LOCAL_LLM_MAX_NEW_TOKENS", "300"))

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
