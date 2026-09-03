from __future__ import annotations

import re
from dataclasses import dataclass

from .models import RetrievedChunk


STOPWORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "the", "to", "was", "with"}


@dataclass(frozen=True)
class FaithfulnessResult:
    is_faithful: bool
    supported_ratio: float
    unsupported_terms: tuple[str, ...]


def evaluate_faithfulness(answer: str, evidence: tuple[RetrievedChunk, ...], minimum_ratio: float = 0.6) -> FaithfulnessResult:
    """Conservative deterministic gate for local and hosted answers.

    It is not a replacement for a semantic LLM-as-judge evaluation, but prevents an answer
    containing unsupported named terms or numbers from being returned to the user.
    """
    evidence_terms = set(re.findall(r"[a-z0-9]+", " ".join(item.chunk.text for item in evidence).lower()))
    answer_terms = [term for term in re.findall(r"[a-z0-9]+", answer.lower()) if len(term) > 2 and term not in STOPWORDS]
    if not answer_terms:
        return FaithfulnessResult(False, 0.0, ())
    unsupported = tuple(sorted({term for term in answer_terms if term not in evidence_terms}))
    ratio = (len(answer_terms) - len(unsupported)) / len(answer_terms)
    return FaithfulnessResult(ratio >= minimum_ratio, ratio, unsupported)
