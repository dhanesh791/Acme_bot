from __future__ import annotations

import hashlib
from collections import defaultdict

from .models import Chunk, ExtractedRecord, SourceMetadata


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


def _chunk_text_record(record: ExtractedRecord, max_chars: int, overlap_chars: int) -> list[Chunk]:
    text = record.text
    if len(text) <= max_chars:
        pieces = [text]
    else:
        step = max(1, max_chars - overlap_chars)
        pieces = [text[index : index + max_chars] for index in range(0, len(text), step)]
    return [Chunk(_chunk_id(piece, record.source), piece, record.source) for piece in pieces]
