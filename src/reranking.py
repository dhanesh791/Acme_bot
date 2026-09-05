from __future__ import annotations

import functools
from dataclasses import replace
from typing import Protocol

from .config import MODEL_CACHE_DIR
from .models import RetrievedChunk


class Reranker(Protocol):
    def rerank(self, question: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


class NoopReranker:
    """Identity reranker: keeps the retrieval order unchanged. Used in tests, and as a
    fast fallback when the real reranker model is intentionally disabled."""

    def rerank(self, question: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return candidates


@functools.lru_cache(maxsize=4)
def _load_cross_encoder(model_name: str):
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(model_name=model_name, cache_dir=MODEL_CACHE_DIR)


class CrossEncoderReranker:
    """Reorders candidates by a real (question, chunk) relevance model via a small
    local ONNX cross-encoder - no API key, no torch. The model is loaded lazily on
    first use and cached per process (see `_load_cross_encoder`), so constructing
    this reranker is cheap even if it never actually gets called.

    Cross-encoder scores are unbounded relevance logits, not the 0-1 cosine score
    used for the initial threshold gate - but they are also a materially more
    reliable relevance judgment on short, structured chunk text (e.g. "Field: value |
    Field: value" table rows), where cosine similarity between a real embedding
    provider's vectors can stay misleadingly high for genuinely unrelated questions
    (confirmed empirically: an unrelated question scored 0.52 cosine against an
    unrelated chunk - comfortably "positive" - while the same pair scored -11.4 under
    this reranker). Each returned chunk carries its `rerank_score` so the caller can
    apply a second, reranker-calibrated no-answer gate on top of the cosine one.
    """

    def __init__(self, model_name: str = "Xenova/ms-marco-MiniLM-L-6-v2") -> None:
        self.model_name = model_name

    def rerank(self, question: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not candidates:
            return candidates
        model = _load_cross_encoder(self.model_name)
        texts = [item.chunk.text for item in candidates]
        scores = list(model.rerank(question, texts))
        scored = [replace(candidate, rerank_score=float(score)) for candidate, score in zip(candidates, scores)]
        return sorted(scored, key=lambda item: item.rerank_score, reverse=True)
