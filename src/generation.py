from __future__ import annotations

import json
import urllib.request

from .models import RetrievedChunk


SYSTEM_PROMPT = """You answer only from the supplied retrieved context. Do not invent facts, calculations, or citations.
If context is insufficient, answer exactly: I can't answer that from the indexed documents.
Give a concise direct answer; citations are rendered separately by the application."""


class OpenAIAnswerGenerator:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def generate(self, question: str, evidence: tuple[RetrievedChunk, ...]) -> str:
        context = "\n\n".join(
            f"[Source {index + 1}: {item.chunk.source.citation()}]\n{item.chunk.text}"
            for index, item in enumerate(evidence)
        )
        body = {"model": self.model, "temperature": 0, "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {question}\n\nRetrieved context:\n{context}"},
        ]}
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload["choices"][0]["message"]["content"].strip()
