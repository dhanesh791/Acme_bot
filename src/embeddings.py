from __future__ import annotations

import functools
import hashlib
import math
import re
import json
import urllib.request
from collections import Counter
from typing import Protocol

from .config import PROJECT_ROOT

# fastembed defaults to tempfile.gettempdir() when no cache_dir is given, which on
# Windows means the OS or a cleanup tool can silently wipe the ~65-150MB cached model
# and force a re-download. Use the same stable data/ directory the rest of the app
# already relies on for persistent storage (LanceDB, logs).
MODEL_CACHE_DIR = str(PROJECT_ROOT / "data" / "model_cache")


class EmbeddingProvider(Protocol):
    model_name: str

    def embed(self, text: str) -> list[float]: ...
    def embed_many(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    """Deterministic local embeddings for a zero-credential prototype."""

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions
        self.model_name = f"local-hash-{dimensions}"

    def embed(self, text: str) -> list[float]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        counts = Counter(tokens)
        vector = [0.0] * self.dimensions
        for token, count in counts.items():
            index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % self.dimensions
            vector[index] += 1.0 + math.log(count)
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


@functools.lru_cache(maxsize=4)
def _load_fastembed_model(model_name: str):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name, cache_dir=MODEL_CACHE_DIR)


class FastEmbedEmbeddingProvider:
    """Local semantic embeddings via a small ONNX model - no API key, no torch.

    The model is loaded lazily on first use (and cached per process by
    `_load_fastembed_model`), so constructing this provider is cheap even if it is
    never actually called, e.g. in tests that override `.embeddings` before use.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self._model_name = model_name
        self.model_name = f"fastembed-{model_name}"

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        model = _load_fastembed_model(self._model_name)
        return [vector.tolist() for vector in model.embed(texts)]


class OpenAIEmbeddingProvider:
    """Minimal OpenAI embeddings adapter; used only when credentials are configured."""

    def __init__(self, api_key: str, model_name: str) -> None:
        self.api_key = api_key
        self.model_name = model_name

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        request = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=json.dumps({"model": self.model_name, "input": texts}).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [item["embedding"] for item in sorted(payload["data"], key=lambda item: item["index"])]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError(
            f"Embedding dimension mismatch ({len(left)} vs {len(right)}); "
            "the index was likely built with a different embedding model."
        )
    return sum(a * b for a, b in zip(left, right))
