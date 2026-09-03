from __future__ import annotations

import hashlib
import math
import re
import json
import urllib.request
from collections import Counter
from typing import Protocol


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
