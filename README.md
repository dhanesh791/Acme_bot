# Acme Retail Multi-Format RAG Chatbot

A small interview prototype for asking grounded questions across CSV, Excel, PowerPoint, and Word files.

> **Scope note:** the original brief ([RAG_Multi_Format_Document_Chatbot_Use_Case.md](RAG_Multi_Format_Document_Chatbot_Use_Case.md)) covers Excel, CSV, and PowerPoint only. Word (`.docx`) support was added afterward at explicit request; see `tasks.md` §10 for the decision record.

## What it does

- Upload and index `.csv`, `.xlsx`, `.pptx`, and `.docx` documents.
- Preserve source metadata: file, CSV row, Excel sheet/row range, PowerPoint slide/title, and Word section/paragraph range.
- Retrieve with a hybrid dense-vector + BM25 pipeline, cross-encoder reranking, and MMR diversity selection, and return only retrieved evidence.
- Show citations and inspect the exact retrieved chunks in the chat UI.
- Decline questions that lack relevant indexed evidence.

Legacy `.xls`, `.ppt`, and `.doc` files are detected but intentionally require conversion to modern formats for this prototype. PowerPoint speaker notes are extracted when present and exposed by the library. Word documents are parsed in document order: `Heading n`-styled paragraphs become section boundaries, body paragraphs are grouped under their nearest preceding heading, and tables are extracted row-by-row independently of surrounding prose.

## Run it

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local address Streamlit prints. Upload the four files in `sample_data/`, click **Index uploaded files**, then ask: `What was South region's Q1 revenue and target attainment?`

## Design

`src/parsers.py` converts each format into normalized records. `src/chunking.py` creates table-aware row-range chunks or paragraph/sentence-aware text chunks while retaining source metadata - oversized free text splits at sentence boundaries (with overlap), not raw character cuts. `src/vector_store.py` persists vectors and metadata locally in LanceDB under `data/lance/`, alongside a BM25 full-text index kept in sync on every write; `src/service.py` retrieves evidence and produces the grounded response.

### Retrieval pipeline

Every question runs through the same five stages (`src/service.py`, `src/vector_store.py`, `src/reranking.py`):

1. **Hybrid retrieval** - dense vector search and BM25 full-text search run in parallel against the same LanceDB table, fused by Reciprocal Rank Fusion (`RRF_K`, default 60). Every fused candidate is then re-scored by real cosine similarity to the query, so the result carries one familiar 0-1 score regardless of which lane found it.
2. **Threshold gate** - candidates below `MIN_RETRIEVAL_SCORE` (default 0.12) are dropped; if nothing clears it, the app returns the no-answer response. When the local hash embedding provider is active, an additional lexical-overlap check applies here too - hashed bag-of-words embeddings can produce meaningfully nonzero cosine similarity between unrelated text purely from hash collisions (confirmed empirically), which a real embedding provider doesn't need guarding against.
3. **Cross-encoder rerank + a second gate** - a small local ONNX model (`RERANKER_MODEL`, default `Xenova/ms-marco-MiniLM-L-6-v2` via `fastembed`) scores each (question, chunk) pair directly, reorders the threshold-passed candidates by that judgment, and anything below `MIN_RERANK_SCORE` (default 0.0) is dropped as a second no-answer gate. This turned out to be necessary, not just a quality nicety: on short, structured chunk text ("Field: value | Field: value" rows), cosine similarity between a real embedding provider's vectors can stay misleadingly high for a genuinely unrelated question - confirmed empirically at 0.52 cosine (comfortably "positive") for a pair the reranker correctly scored -11.4. Set `USE_RERANKER=false` to skip both (falls back to retrieval order, no second gate).
4. **MMR diversity selection** - Maximal Marginal Relevance (`MMR_LAMBDA`, default 0.65) picks the final `RETRIEVAL_TOP_K` chunks by balancing rerank-order relevance against real embedding-similarity to what's already been picked, so near-duplicate chunks (e.g. adjacent table rows repeating the same fields) don't crowd out coverage of other sources.
5. **Generation** - grounded LLM prompt (if `OPENAI_API_KEY` is set) or the extractive fallback, unchanged from before.

Embeddings themselves (`src/embeddings.py`) follow `EMBEDDING_PROVIDER` (default `auto`): OpenAI when a key is configured, otherwise a real local semantic model (`LOCAL_EMBEDDING_MODEL`, default `BAAI/bge-small-en-v1.5` via `fastembed` - no API key, no torch, ~67MB, downloaded once and cached). `EMBEDDING_PROVIDER=hash` forces the older deterministic hashed-bag-of-words provider (zero download, what the test suite uses for speed); it's not the default anymore because it's materially worse at genuine semantic matching than either real option. The app refuses to mix embedding models in one knowledge base regardless of which provider is active - switch providers by clearing the knowledge base first, not mid-session.

### Metadata and storage

Rows, slides, and paragraphs use one-based positions. CSV and Excel citations show `file -> sheet (when present) -> row N-M`; PowerPoint citations show `file -> Slide N (title)`; Word citations show `file -> section (when present) -> paragraph N-M` for body text, or `file -> section - Table k -> row N` for a table row. Metadata remains attached to each LanceDB vector and can filter retrieval by file, format, sheet, slide, or Word section.

Each browser session receives its own LanceDB namespace under `data/lance/`; clearing the knowledge base deletes only that session's namespace. Uploaded bytes are processed in memory and are not retained by the application. Local index files and logs are excluded from Git. This prototype has no authentication, so it should not be exposed as a shared public deployment.

The browser session is the access boundary. Session indexes are automatically removed after 24 hours by default (`SESSION_RETENTION_HOURS` configures this). In a real deployment, authenticate users, associate each namespace with an account/tenant, encrypt storage, and run retention cleanup as a scheduled job. Do not place sensitive documents in a publicly reachable instance.

### Optional OpenAI mode

Copy `.env.example` to `.env` and configure `OPENAI_API_KEY` before starting the app (`.env` is loaded automatically via `python-dotenv`). The app then uses OpenAI embeddings and a zero-temperature grounded-generation prompt on top of the same hybrid-retrieval-plus-rerank pipeline. Without a key it still does real semantic retrieval (local FastEmbed embeddings, hybrid search, reranking) but returns retrieved evidence verbatim as the answer instead of LLM prose, since there's no model to generate with.

A generated answer is only shown if it passes a deterministic faithfulness check (`src/evaluation.py`) against the retrieved evidence and is not itself a refusal; otherwise the app logs a warning and falls back to the extractive answer. An existing knowledge base remembers which embedding model indexed it (`embedding_model` per chunk); indexing or asking questions with a different provider is refused with a message to clear the knowledge base first, rather than silently corrupting retrieval scores.

## Validation

```powershell
python -m pytest -q
```

The tests cover CSV metadata, chunk row ranges, unsupported/legacy errors, retrieval with citations, no-answer behavior, embedding-model mismatch guards, stubbed OpenAI embedding/generation calls, and the hybrid retrieval/reranking/MMR pipeline - including a couple of real (not mocked) tests against the small local FastEmbed and cross-encoder models, since those are local dependencies rather than a paid API. First run downloads ~150MB of cached ONNX models; offline and fast on every run after that.

If pytest fails with a Windows `PermissionError`/`WinError 5` under a long path (common when the project lives inside OneDrive), it is a `tmp_path`/LanceDB `MAX_PATH` issue, not a code failure. Point pytest at a short base directory instead:

```powershell
python -m pytest -q --basetemp=C:\pt
```
