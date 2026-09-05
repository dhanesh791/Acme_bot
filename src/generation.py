from __future__ import annotations

import functools
import json
import urllib.request
from pathlib import Path
from typing import Protocol

from .config import MODEL_CACHE_DIR
from .models import RetrievedChunk


class AnswerGenerator(Protocol):
    model_name: str

    def generate(self, question: str, evidence: tuple[RetrievedChunk, ...]) -> str: ...


SYSTEM_PROMPT = """You answer only from the supplied retrieved context. Do not invent facts, calculations, or citations.
If context is insufficient, answer exactly: I can't answer that from the indexed documents.
Give a concise direct answer; citations are rendered separately by the application."""


def _build_context(evidence: tuple[RetrievedChunk, ...]) -> str:
    return "\n\n".join(
        f"[Source {index + 1}: {item.chunk.source.citation()}]\n{item.chunk.text}"
        for index, item in enumerate(evidence)
    )


class OpenAIAnswerGenerator:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self.model_name = model

    def generate(self, question: str, evidence: tuple[RetrievedChunk, ...]) -> str:
        context = _build_context(evidence)
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


@functools.lru_cache(maxsize=1)
def _load_local_llm(repo_id: str, variant: str):
    """Download (once) and load a local ONNX chat model for fully offline generation.

    Uses `local_dir`, not `cache_dir`: huggingface_hub's default cache layer symlinks
    each file from a content-addressed blob store, which fails outright on Windows
    without Developer Mode or admin rights (confirmed empirically - see ISSUES.md).
    `local_dir` downloads straight into a plain folder and sidesteps that entirely.
    """
    import onnxruntime_genai as og
    from huggingface_hub import snapshot_download

    target = Path(MODEL_CACHE_DIR) / repo_id.replace("/", "--")
    snapshot_download(repo_id=repo_id, allow_patterns=[f"{variant}/*"], local_dir=str(target))
    model = og.Model(str(target / variant))
    tokenizer = og.Tokenizer(model)
    return model, tokenizer


class LocalLLMGenerator:
    """Fully local grounded generation via a small quantized chat model (default:
    Phi-3.5-mini-instruct, int4, ONNX) through onnxruntime-genai - no API key, no
    network needed at answer time, but a much larger one-time download (~2.8GB for
    the default model) and noticeably slower per-answer latency than OpenAI, since
    inference runs on CPU. Lazily loaded and cached per process (see
    `_load_local_llm`), so constructing this is cheap even if it's never called -
    the download only happens on first actual use.
    """

    def __init__(self, repo_id: str, variant: str, max_new_tokens: int = 300) -> None:
        self.repo_id = repo_id
        self.variant = variant
        self.max_new_tokens = max_new_tokens
        self.model_name = f"local-llm-{repo_id.split('/')[-1]}"

    def generate(self, question: str, evidence: tuple[RetrievedChunk, ...]) -> str:
        import onnxruntime_genai as og

        model, tokenizer = _load_local_llm(self.repo_id, self.variant)
        context = _build_context(evidence)
        messages = json.dumps([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {question}\n\nRetrieved context:\n{context}"},
        ])
        prompt = tokenizer.apply_chat_template(messages=messages, add_generation_prompt=True)
        tokens = tokenizer.encode(prompt)

        params = og.GeneratorParams(model)
        params.set_search_options(max_length=len(tokens) + self.max_new_tokens, temperature=0.001, do_sample=False)
        generator = og.Generator(model, params)
        generator.append_tokens(tokens)
        output_tokens: list[int] = []
        while not generator.is_done():
            generator.generate_next_token()
            output_tokens.append(generator.get_next_tokens()[0])
        return tokenizer.decode(output_tokens).strip()
