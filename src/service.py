from __future__ import annotations

import time
import re
import shutil

from .chunking import chunk_records
from .config import Settings, settings
from .embeddings import (
    EmbeddingProvider,
    FastEmbedEmbeddingProvider,
    HashEmbeddingProvider,
    OpenAIEmbeddingProvider,
    cosine_similarity,
)
from .evaluation import evaluate_faithfulness
from .generation import OpenAIAnswerGenerator
from .logging_config import logger
from .models import ChatResponse, IndexingResult, RetrievedChunk, SourceMetadata
from .parsers import parse_document
from .reranking import CrossEncoderReranker, NoopReranker, Reranker
from .vector_store import LocalVectorStore


NO_ANSWER = "I can't answer that from the indexed documents. Please upload a source that contains the needed information."
GUARDRAIL_REFUSAL = "I can't help with that request. Please ask a factual question about the indexed business documents."
MAX_QUESTION_CHARS = 1_000
INJECTION_PATTERNS = (r"ignore (all |any |the )?(previous|prior|above) instructions", r"reveal (the )?(system|hidden) prompt", r"act as (a )?(system|developer)")
UNSAFE_PATTERNS = (r"\b(build|make|obtain)\b.*\b(bomb|weapon|malware)\b", r"\b(dox|steal|exfiltrate)\b.*\b(data|password|credential)\b")


def _select_embedding_provider(app_settings: Settings) -> EmbeddingProvider:
    """embedding_provider="auto" prefers OpenAI when a key is configured, otherwise the
    local FastEmbed model. "hash"/"local"/"openai" force a specific provider regardless
    of key presence - tests use "hash" for a fast, deterministic, zero-download provider."""
    provider = app_settings.embedding_provider
    if provider == "hash":
        return HashEmbeddingProvider(app_settings.embedding_dimensions)
    if provider == "openai" or (provider == "auto" and app_settings.openai_api_key):
        if not app_settings.openai_api_key:
            raise ValueError("embedding_provider='openai' requires OPENAI_API_KEY to be set.")
        return OpenAIEmbeddingProvider(app_settings.openai_api_key, app_settings.openai_embedding_model)
    if provider in ("auto", "local"):
        return FastEmbedEmbeddingProvider(app_settings.local_embedding_model)
    raise ValueError(f"Unknown embedding_provider setting: '{provider}'.")


def _select_reranker(app_settings: Settings) -> Reranker:
    return CrossEncoderReranker(app_settings.reranker_model) if app_settings.use_reranker else NoopReranker()


class RagService:
    def __init__(self, app_settings: Settings = settings, workspace_id: str = "default") -> None:
        self.settings = app_settings
        self.embeddings: EmbeddingProvider = _select_embedding_provider(app_settings)
        self.reranker: Reranker = _select_reranker(app_settings)
        self.generator = OpenAIAnswerGenerator(app_settings.openai_api_key, app_settings.openai_chat_model) if app_settings.openai_api_key else None
        self.store = LocalVectorStore(app_settings.index_path / workspace_id)

    def health_check(self) -> dict[str, str | bool]:
        return {
            "status": "ready",
            "embedding_provider": self.embeddings.model_name,
            "reranker": type(self.reranker).__name__,
            "answer_mode": "OpenAI grounded generation" if self.generator else "Local extractive fallback",
            "api_key_configured": bool(self.settings.openai_api_key),
            "vector_store": "LanceDB (hybrid vector + BM25)",
        }

    @staticmethod
    def cleanup_expired_workspaces(app_settings: Settings = settings) -> int:
        """Remove only session index folders older than the configured retention period."""
        root = app_settings.index_path
        if not root.exists():
            return 0
        cutoff = time.time() - app_settings.session_retention_hours * 3600
        removed = 0
        for workspace in root.iterdir():
            if workspace.is_dir() and workspace.stat().st_mtime < cutoff:
                shutil.rmtree(workspace)
                removed += 1
        if removed:
            logger.info("expired session indexes removed=%s", removed)
        return removed

    def index_document(self, file_name: str, payload: bytes) -> IndexingResult:
        if len(payload) > self.settings.max_upload_bytes:
            raise ValueError(f"'{file_name}' exceeds the {self.settings.max_upload_bytes // 1024 // 1024} MB upload limit.")
        existing_models = self.store.embedding_models()
        if existing_models and self.embeddings.model_name not in existing_models:
            raise ValueError(
                f"This knowledge base was indexed with {', '.join(sorted(existing_models))}; "
                f"the active embedding provider is '{self.embeddings.model_name}'. "
                "Clear the knowledge base before indexing with a different embedding model."
            )
        started = time.perf_counter()
        try:
            records = parse_document(file_name, payload)
            document_id = records[0].source.document_id
            warnings = tuple(sorted({warning for record in records for warning in record.warnings}))
            if self.store.has_document_id(document_id):
                return IndexingResult(file_name, document_id, "unchanged", len(records), 0, warnings)
            status = "replaced" if file_name in self.store.documents() else "indexed"
            chunks = chunk_records(records, self.settings.chunk_rows, self.settings.chunk_max_chars)
            vectors = self._embed_in_batches([chunk.text for chunk in chunks])
            self.store.upsert(chunks, vectors, self.embeddings.model_name)
            logger.info("indexed file=%s records=%s chunks=%s elapsed_ms=%.0f", file_name, len(records), len(chunks), (time.perf_counter() - started) * 1000)
            return IndexingResult(file_name, document_id, status, len(records), len(chunks), warnings)
        except Exception:
            logger.exception("indexing failed file=%s", file_name)
            raise

    def answer(self, question: str, filters: dict[str, str | int] | None = None) -> ChatResponse:
        question = question.strip()
        if not question:
            return ChatResponse(answer=NO_ANSWER, is_no_answer=True)
        blocked = (*INJECTION_PATTERNS, *UNSAFE_PATTERNS)
        if len(question) > MAX_QUESTION_CHARS or any(re.search(pattern, question, re.IGNORECASE) for pattern in blocked):
            logger.warning("guardrail refusal query_chars=%s", len(question))
            return ChatResponse(answer=GUARDRAIL_REFUSAL, is_no_answer=True)
        existing_models = self.store.embedding_models()
        if existing_models and self.embeddings.model_name not in existing_models:
            logger.warning("embedding model mismatch stored=%s active=%s", existing_models, self.embeddings.model_name)
            return ChatResponse(
                answer=(
                    "The knowledge base was indexed with a different embedding model "
                    f"({', '.join(sorted(existing_models))}). Clear the knowledge base and re-index before asking questions."
                ),
                is_no_answer=True,
            )
        started = time.perf_counter()
        retrieved = self.store.search(
            question,
            self.embeddings.embed(question),
            self.settings.rerank_candidate_pool,
            filters,
            rrf_k=self.settings.rrf_k,
        )
        logger.info("retrieval query_chars=%s candidates=%s elapsed_ms=%.0f", len(question), len(retrieved), (time.perf_counter() - started) * 1000)
        # Hybrid retrieval (dense vector + BM25 full-text) covers lexical matching, so
        # this gate is not about finding lexical matches. It exists for a different
        # reason: the local hash embedding's 256-dim hashed-bag-of-words geometry
        # produces real, meaningfully nonzero cosine "similarity" between genuinely
        # unrelated texts purely from hash collisions (confirmed empirically: an
        # unrelated question scored 0.29 against an unrelated chunk, comfortably above
        # the 0.12 threshold). A real embedding provider doesn't have this failure
        # mode, so the gate only applies to the hash provider.
        requires_lexical_overlap = isinstance(self.embeddings, HashEmbeddingProvider)
        threshold_passed = [
            match for match in retrieved
            if match.score >= self.settings.min_retrieval_score
            and (not requires_lexical_overlap or _has_lexical_overlap(question, match.chunk.text))
        ]
        if not threshold_passed:
            return ChatResponse(answer=NO_ANSWER, evidence=tuple(retrieved), is_no_answer=True)
        rerank_started = time.perf_counter()
        reranked = self.reranker.rerank(question, threshold_passed)
        logger.info("rerank candidates=%s elapsed_ms=%.0f", len(reranked), (time.perf_counter() - rerank_started) * 1000)
        # A real reranker's relevance judgment is materially more reliable than cosine
        # similarity alone on short, structured chunk text (e.g. "Field: value | Field:
        # value" rows), where an unrelated question can still score misleadingly high
        # on cosine (confirmed empirically - see src/reranking.py). Apply a second gate
        # on rerank_score when one was actually computed; NoopReranker leaves it None,
        # so this is a no-op when reranking is disabled.
        rerank_gated = [item for item in reranked if item.rerank_score is None or item.rerank_score >= self.settings.min_rerank_score]
        if not rerank_gated:
            return ChatResponse(answer=NO_ANSWER, evidence=tuple(threshold_passed), is_no_answer=True)
        evidence = tuple(_mmr_select(rerank_gated, self.settings.retrieval_top_k, self.settings.mmr_lambda))
        sources = _unique_sources(evidence)
        answer = _extractive_answer(evidence)
        if self.generator:
            try:
                generated = self.generator.generate(question, evidence)
                if _is_llm_refusal(generated):
                    return ChatResponse(answer=NO_ANSWER, evidence=evidence, is_no_answer=True)
                evaluation = evaluate_faithfulness(generated, evidence)
                if evaluation.is_faithful:
                    answer = generated
                else:
                    logger.warning("generation failed faithfulness gate supported_ratio=%.2f", evaluation.supported_ratio)
            except Exception:
                logger.exception("generation failed; returning extractive fallback")
        return ChatResponse(answer=answer, sources=sources, evidence=evidence, is_no_answer=False)

    def _embed_in_batches(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.settings.embedding_batch_size):
            batch = texts[start : start + self.settings.embedding_batch_size]
            for attempt in range(1, self.settings.embedding_max_retries + 1):
                try:
                    vectors.extend(self.embeddings.embed_many(batch))
                    break
                except Exception:
                    if attempt == self.settings.embedding_max_retries:
                        logger.exception("embedding failed batch_start=%s attempts=%s", start, attempt)
                        raise
                    time.sleep(0.5 * attempt)
        return vectors


LLM_REFUSAL_PREFIX = "i can't answer that from the indexed documents"


def _is_llm_refusal(generated_answer: str) -> bool:
    return generated_answer.strip().lower().startswith(LLM_REFUSAL_PREFIX)


def _unique_sources(evidence: tuple[RetrievedChunk, ...]) -> tuple[SourceMetadata, ...]:
    seen: set[str] = set()
    sources: list[SourceMetadata] = []
    for item in evidence:
        citation = item.chunk.source.citation()
        if citation not in seen:
            seen.add(citation)
            sources.append(item.chunk.source)
    return tuple(sources)


STOPWORDS = {"a", "an", "and", "are", "as", "at", "do", "for", "from", "how", "i", "in", "is", "of", "on", "the", "to", "was", "what", "when", "where", "who", "with"}


def _has_lexical_overlap(question: str, chunk_text: str) -> bool:
    question_terms = {term for term in re.findall(r"[a-z0-9]+", question.lower()) if len(term) > 2 and term not in STOPWORDS}
    chunk_terms = set(re.findall(r"[a-z0-9]+", chunk_text.lower()))
    return bool(question_terms & chunk_terms)


def _extractive_answer(evidence: tuple[RetrievedChunk, ...]) -> str:
    """Honest no-key fallback: presents retrieved facts verbatim instead of fabricating prose."""
    snippets = [item.chunk.text.replace("\n", " ") for item in evidence[:2]]
    return "Based on the indexed evidence: " + " ".join(snippets)


def _mmr_select(ranked_candidates: list[RetrievedChunk], limit: int, lambda_mult: float) -> list[RetrievedChunk]:
    """Maximal Marginal Relevance over an already relevance-ranked candidate list
    (post-rerank order, best first). Relevance is taken from rank position rather
    than the raw per-candidate score, since reranking may have reordered candidates
    using a different, incomparable score scale (cross-encoder logits vs. cosine).
    Diversity is real cosine similarity between chunk embeddings, so near-duplicate
    chunks (e.g. adjacent table rows repeating the same fields) don't crowd out
    coverage of other sources - replaces the old hard per-source cap with an actual
    semantic diversity measure.
    """
    if not ranked_candidates:
        return []
    pool_size = len(ranked_candidates)
    relevance = {id(candidate): 1.0 - (rank / pool_size) for rank, candidate in enumerate(ranked_candidates)}
    selected: list[RetrievedChunk] = []
    remaining = list(ranked_candidates)

    def mmr_score(candidate: RetrievedChunk) -> float:
        if not selected or candidate.vector is None:
            diversity_penalty = 0.0
        else:
            diversity_penalty = max(
                (cosine_similarity(candidate.vector, chosen.vector) for chosen in selected if chosen.vector is not None),
                default=0.0,
            )
        return lambda_mult * relevance[id(candidate)] - (1 - lambda_mult) * diversity_penalty

    while remaining and len(selected) < limit:
        best = max(remaining, key=mmr_score)
        selected.append(best)
        remaining.remove(best)
    return selected
