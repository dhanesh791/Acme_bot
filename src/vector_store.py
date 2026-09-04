from __future__ import annotations

from pathlib import Path

import lancedb
from lancedb.index import FTS

from .embeddings import cosine_similarity
from .logging_config import logger
from .models import Chunk, RetrievedChunk, SourceMetadata


class LocalVectorStore:
    """Persistent LanceDB vector store for the local prototype."""

    collection_name = "acme_document_chunks"

    def __init__(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.database = lancedb.connect(str(path))

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]], embedding_model: str) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("Each chunk must have exactly one embedding vector.")
        entries = [_entry_for_lance(chunk, vector, embedding_model) for chunk, vector in zip(chunks, vectors)]
        if not self._exists():
            table = self.database.create_table(self.collection_name, entries)
        else:
            table = self.database.open_table(self.collection_name)
            replaced_files = {chunk.source.file_name for chunk in chunks}
            for file_name in replaced_files:
                table.delete(f"file_name = '{file_name.replace("'", "''")}'")
            table.add(entries)
        self._rebuild_fts_index(table)
        return len(chunks)

    def _rebuild_fts_index(self, table) -> None:
        """Keep the BM25 full-text index in sync after every write. Cheap enough for a
        prototype's write volume; a real deployment would batch/schedule this instead."""
        try:
            table.create_index("text", config=FTS(), replace=True)
        except Exception:
            logger.exception("failed to build full-text search index; hybrid retrieval will fall back to vector-only")

    def search(
        self,
        query_text: str,
        query_vector: list[float],
        top_k: int,
        filters: dict[str, str | int] | None = None,
        rrf_k: int = 60,
    ) -> list[RetrievedChunk]:
        """Hybrid retrieval: fuse dense vector search and BM25 full-text search via
        Reciprocal Rank Fusion for better candidate recall, then re-score every fused
        candidate by real cosine similarity to the query vector - so downstream
        thresholding/MMR keep the same familiar 0-1 scale regardless of which lane(s)
        actually found a given candidate.
        """
        if not self._exists():
            return []
        table = self.database.open_table(self.collection_name)
        where = _where_clause(filters or {})

        vector_query = table.search(query_vector).limit(top_k)
        if where:
            vector_query = vector_query.where(where)
        vector_hits = vector_query.to_list()

        fts_hits: list[dict] = []
        if query_text.strip():
            try:
                fts_query = table.search(query_text, query_type="fts").limit(top_k)
                if where:
                    fts_query = fts_query.where(where)
                fts_hits = fts_query.to_list()
            except Exception:
                logger.exception("full-text search failed; continuing with vector-only results")

        fused_ranks: dict[str, float] = {}
        entries_by_id: dict[str, dict] = {}
        for rank, entry in enumerate(vector_hits, start=1):
            fused_ranks[entry["chunk_id"]] = fused_ranks.get(entry["chunk_id"], 0.0) + 1.0 / (rrf_k + rank)
            entries_by_id[entry["chunk_id"]] = entry
        for rank, entry in enumerate(fts_hits, start=1):
            fused_ranks[entry["chunk_id"]] = fused_ranks.get(entry["chunk_id"], 0.0) + 1.0 / (rrf_k + rank)
            entries_by_id.setdefault(entry["chunk_id"], entry)

        matches: list[RetrievedChunk] = []
        for chunk_id in fused_ranks:
            entry = entries_by_id[chunk_id]
            vector = entry["vector"]
            matches.append(
                RetrievedChunk(
                    Chunk(entry["chunk_id"], entry["text"], _source_from_lance(entry)),
                    cosine_similarity(query_vector, vector),
                    tuple(vector),
                )
            )
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:top_k]

    def clear(self) -> None:
        if self._exists():
            self.database.drop_table(self.collection_name)

    def document_count(self) -> int:
        return len({entry["document_id"] for entry in self._all_entries()})

    def documents(self) -> list[str]:
        return sorted({entry["file_name"] for entry in self._all_entries()})

    def has_document_id(self, document_id: str) -> bool:
        return any(entry["document_id"] == document_id for entry in self._all_entries())

    def embedding_models(self) -> set[str]:
        """Distinct embedding models present in the index; empty when the index is empty."""
        return {entry["embedding_model"] for entry in self._all_entries()}

    def filter_values(self, field: str) -> list[str | int]:
        values = {entry[field] for entry in self._all_entries() if entry.get(field) not in ("", 0, None)}
        return sorted(values)

    def _exists(self) -> bool:
        return self.collection_name in self.database.list_tables().tables

    def _all_entries(self) -> list[dict]:
        return self.database.open_table(self.collection_name).to_arrow().to_pylist() if self._exists() else []


def _entry_for_lance(chunk: Chunk, vector: list[float], embedding_model: str) -> dict:
    source = chunk.source
    return {
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "vector": vector,
        "file_name": source.file_name,
        "file_type": source.file_type,
        "document_id": source.document_id,
        "embedding_model": embedding_model,
        "sheet_name": source.sheet_name or "",
        "row_start": source.row_start or 0,
        "row_end": source.row_end or 0,
        "slide_number": source.slide_number or 0,
        "slide_title": source.slide_title or "",
        "section_title": source.section_title or "",
        "paragraph_start": source.paragraph_start or 0,
        "paragraph_end": source.paragraph_end or 0,
    }


def _source_from_lance(entry: dict) -> SourceMetadata:
    return SourceMetadata(
        file_name=entry["file_name"], file_type=entry["file_type"], document_id=entry["document_id"],
        sheet_name=entry["sheet_name"] or None, row_start=entry["row_start"] or None, row_end=entry["row_end"] or None,
        slide_number=entry["slide_number"] or None, slide_title=entry["slide_title"] or None,
        section_title=entry["section_title"] or None,
        paragraph_start=entry["paragraph_start"] or None, paragraph_end=entry["paragraph_end"] or None,
    )


ALLOWED_FILTERS = {"file_name", "file_type", "sheet_name", "slide_number", "section_title"}


def _where_clause(filters: dict[str, str | int]) -> str | None:
    clauses: list[str] = []
    for field, value in filters.items():
        if field not in ALLOWED_FILTERS or value in ("", None):
            continue
        if field == "slide_number":
            if not isinstance(value, int) or value < 1:
                raise ValueError("slide_number must be a positive integer.")
            clauses.append(f"{field} = {value}")
        elif isinstance(value, str):
            clauses.append(f"{field} = '{value.replace("'", "''")}'")
        else:
            raise ValueError(f"Invalid filter value for {field}.")
    return " AND ".join(clauses) or None
