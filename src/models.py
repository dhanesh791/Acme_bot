from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceMetadata:
    file_name: str
    file_type: str
    document_id: str
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    slide_number: int | None = None
    slide_title: str | None = None
    section_title: str | None = None
    paragraph_start: int | None = None
    paragraph_end: int | None = None

    def citation(self) -> str:
        parts = [self.file_name]
        if self.sheet_name:
            parts.append(self.sheet_name)
        if self.section_title:
            parts.append(self.section_title)
        if self.row_start is not None:
            row_range = str(self.row_start)
            if self.row_end is not None and self.row_end != self.row_start:
                row_range += f"-{self.row_end}"
            parts.append(f"row {row_range}")
        if self.paragraph_start is not None:
            para_range = str(self.paragraph_start)
            if self.paragraph_end is not None and self.paragraph_end != self.paragraph_start:
                para_range += f"-{self.paragraph_end}"
            parts.append(f"paragraph {para_range}")
        if self.slide_number is not None:
            slide = f"Slide {self.slide_number}"
            if self.slide_title:
                slide += f" ({self.slide_title})"
            parts.append(slide)
        return " -> ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceMetadata":
        return cls(**data)


@dataclass(frozen=True)
class ExtractedRecord:
    text: str
    source: SourceMetadata
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    source: SourceMetadata

    def to_dict(self) -> dict[str, Any]:
        return {"chunk_id": self.chunk_id, "text": self.text, "source": self.source.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Chunk":
        return cls(chunk_id=data["chunk_id"], text=data["text"], source=SourceMetadata.from_dict(data["source"]))


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float
    vector: tuple[float, ...] | None = None  # carried through for MMR diversity scoring
    rerank_score: float | None = None  # set by a real reranker; None means no reranker ran


@dataclass(frozen=True)
class ChatResponse:
    answer: str
    sources: tuple[SourceMetadata, ...] = field(default_factory=tuple)
    evidence: tuple[RetrievedChunk, ...] = field(default_factory=tuple)
    is_no_answer: bool = False
    used_extractive_fallback: bool = False  # a generated answer was rejected (or failed) and the extractive fallback is shown instead


@dataclass(frozen=True)
class IndexingResult:
    file_name: str
    document_id: str
    status: str
    record_count: int
    chunk_count: int
    warnings: tuple[str, ...] = ()
