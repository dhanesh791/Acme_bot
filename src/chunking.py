from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from .models import Chunk, ExtractedRecord, SourceMetadata


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _chunk_id(text: str, source: SourceMetadata) -> str:
    seed = (
        f"{source.document_id}|{source.sheet_name}|{source.section_title}|"
        f"{source.row_start}|{source.slide_number}|{source.paragraph_start}|{text}"
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def chunk_records(records: list[ExtractedRecord], rows_per_chunk: int = 6, max_chars: int = 2400, overlap_chars: int = 180) -> list[Chunk]:
    """Keep contiguous table rows together; split long slide/section/text records by size."""
    grouped: dict[tuple[str, str | None, int | None, str | None], list[ExtractedRecord]] = defaultdict(list)
    for record in records:
        source = record.source
        grouped[(source.document_id, source.sheet_name, source.slide_number, source.section_title)].append(record)

    chunks: list[Chunk] = []
    for group_records in grouped.values():
        first_source = group_records[0].source
        if first_source.slide_number is not None or first_source.paragraph_start is not None:
            combined = ExtractedRecord(
                text="\n".join(record.text for record in group_records),
                source=first_source,
                warnings=tuple(warning for record in group_records for warning in record.warnings),
            )
            chunks.extend(_chunk_text_record(combined, max_chars, overlap_chars))
            continue
        batch: list[ExtractedRecord] = []
        for record in group_records:
            candidate = "\n".join(item.text for item in [*batch, record])
            if batch and (len(batch) >= rows_per_chunk or len(candidate) > max_chars):
                chunks.extend(_table_batch_chunks(batch, max_chars))
                batch = []
            if len(record.text) > max_chars:
                chunks.extend(_chunk_text_record(record, max_chars, 0))
            else:
                batch.append(record)
        if batch:
            chunks.extend(_table_batch_chunks(batch, max_chars))
    return chunks


def _table_batch_chunks(batch: list[ExtractedRecord], max_chars: int) -> list[Chunk]:
    text = "\n".join(record.text for record in batch)
    source = SourceMetadata(**{**batch[0].source.to_dict(), "row_start": batch[0].source.row_start, "row_end": batch[-1].source.row_end})
    return [Chunk(_chunk_id(text, source), text, source)]


def _split_into_units(text: str) -> list[str]:
    """Paragraph-then-sentence split, so oversized text breaks at readable boundaries
    instead of mid-word. Falls back to the whole string when no boundary is found
    (e.g. a single long run-on line with no sentence punctuation)."""
    units: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            continue
        units.extend(piece for piece in _SENTENCE_SPLIT.split(paragraph) if piece.strip())
    return units or [text]


def _chunk_text_record(record: ExtractedRecord, max_chars: int, overlap_chars: int) -> list[Chunk]:
    text = record.text
    if len(text) <= max_chars:
        return [Chunk(_chunk_id(text, record.source), text, record.source)]

    pieces: list[str] = []
    current: list[str] = []

    def current_text() -> str:
        return " ".join(current)

    for unit in _split_into_units(text):
        if len(unit) > max_chars:
            # A single sentence longer than the whole budget: close the pending piece,
            # then hard-slice this one as a last resort.
            if current:
                pieces.append(current_text())
                current = []
            step = max(1, max_chars - overlap_chars)
            pieces.extend(unit[index : index + max_chars] for index in range(0, len(unit), step))
            continue
        candidate = f"{current_text()} {unit}".strip() if current else unit
        if current and len(candidate) > max_chars:
            pieces.append(current_text())
            # Seed the next piece with trailing overlap carried from the piece just closed.
            overlap: list[str] = []
            overlap_len = 0
            for prior in reversed(current):
                if overlap_len + len(prior) > overlap_chars:
                    break
                overlap.insert(0, prior)
                overlap_len += len(prior) + 1
            current = overlap
        current.append(unit)

    if current:
        pieces.append(current_text())

    return [Chunk(_chunk_id(piece, record.source), piece, record.source) for piece in pieces]
