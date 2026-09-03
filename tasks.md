# Multi-Format RAG Document Chatbot - Implementation Tasks

## Target outcome

Build a production-oriented Acme Retail prototype that accepts Excel, CSV, and PowerPoint files, indexes their content, and answers questions only from retrieved evidence. Every answer must cite its originating file and the most specific available location (sheet/row range or slide).

## Mental model / architecture

```text
Upload UI
   -> file validation + content fingerprinting
   -> format router
      -> Excel parser | CSV parser | PowerPoint parser
   -> normalized records (content + source metadata)
   -> structure-aware chunker
   -> embedding provider
   -> vector store (vectors + chunks + metadata)

Question UI
   -> query embedding
   -> similarity retrieval (+ optional reranking/filtering)
   -> grounded LLM prompt with retrieved chunks
   -> answer, no-answer decision, and citations
```

The main invariant is traceability: metadata is created at extraction time and stays attached to every record, chunk, vector-store entry, retrieval result, and final citation.

## Current status

Verified against the code on 2026-09-03. All nine gaps found in the review pass (G1-G9) were fixed the same day; see **Gaps found in verification review** below, each now marked Fixed with what changed.

- `python -m pytest -q --basetemp=<short path>` -> **34 passed** (26 original + 8 new tests covering the fixes: OpenAI provider/generator with a stubbed transport, embedding-model mismatch guards on index and query, targeted reindex-without-overwrite, LLM refusal detection, and the slide-group data-loss fix).
- The plain `python -m pytest -q` in the README still errors under this machine's OneDrive path (Windows `MAX_PATH`, not a code defect); README now documents the `--basetemp` workaround.
- The repo is **still not its own git repository** — `git rev-parse --show-toplevel` resolves to `C:/Users/Kakashi` and every file here is untracked. Unchanged by this pass; flagged again in case it matters for the deliverable.

All items below are now checked and hold up against the code as of this pass.

## Acceptance criteria added during review

- [x] Verify multi-format ingestion for CSV, XLSX, PPTX, plus clear legacy XLS/PPT conversion errors.
- [x] Verify source metadata survives parsing, indexing, filtered retrieval, and final citations.
- [x] Add groundedness/faithfulness checks for local extractive answers and optional LLM answers.
- [x] Add guardrails for unsafe, prompt-injection, empty, and out-of-scope questions; enforce safe answer behavior.
- [x] Add corrupt-file regression tests for every supported parser.
- [x] Surface complete per-file indexing results, including warnings and duplicate/replacement state.
- [x] Add metadata filtering by file name, file type, Excel sheet, and PowerPoint slide number.

## Decisions to make before implementation

- [x] Select the application stack and UI framework (Python + Streamlit).
- [x] Select an LLM and embedding provider; define required environment variables and a local-development fallback if feasible.
- [x] Select a persistent vector store (LanceDB) suitable for a small local prototype.
- [x] Define supported versions and behavior for legacy `.xls` and `.ppt` files. Document conversion or a clear unsupported-file message if native parsing is impractical.
- [x] Define storage boundaries: upload directory, index persistence location, document ownership/session scope, and cleanup policy.

## 1. Project foundation

- [x] Initialize the project structure with separate modules for UI, ingestion, parsing, chunking, embeddings, vector storage, retrieval, generation, and shared models.
- [x] Add dependency management, environment-variable configuration, `.env.example`, and `.gitignore` entries for secrets, uploads, and vector-store data. **Fixed (G1):** `python-dotenv` added to `requirements.txt`; `src/config.py` calls `load_dotenv()` before `Settings` reads any env var.
- [x] Create a README covering architecture, prerequisites, setup, running the app, supported formats, and limitations.
- [x] Add structured logging for ingestion failures, indexing counts/duration, retrieval latency, and model/API failures.
- [x] Add a health/configuration check that reports missing model credentials without exposing secrets.

## 2. Canonical data contracts

- [x] Define a normalized extracted-record model with `text`, `file_name`, `file_type`, `document_id`, and location metadata.
- [x] Include optional location fields: `sheet_name`, `row_start`, `row_end`, `slide_number`, `slide_title`, and extraction warnings.
- [x] Define a chunk model that retains `chunk_id`, source-record metadata, chunk text, and content/fingerprint hashes.
- [x] Define response/citation models so UI citations are generated from metadata instead of parsing LLM prose.
- [x] Document metadata conventions, including 1-based row/slide numbering and how ranges are displayed.

## 3. Upload and document lifecycle

- [x] Build a multi-file upload flow accepting `.xlsx`, `.xls`, `.csv`, `.pptx`, and `.ppt`.
- [x] Validate file extension, MIME/type where possible, file size, empty files, and duplicate uploads.
- [x] Generate a stable content fingerprint and skip re-indexing when an identical document has already been indexed in the same knowledge base.
- [x] Report per-file indexing status, chunk count, skipped/updated state, and actionable parse errors.
- [x] Ensure files and indexes are isolated to the current user/session or another explicitly defined access boundary.

## 4. Format parsers

### Excel parser

- [x] Extract every readable worksheet name, column headers, and populated rows from `.xlsx` files.
- [x] Extract formula results where available; clearly handle formulas whose cached result is unavailable.
- [x] Produce table-aware records with sheet name and exact row ranges.
- [x] Support `.xls` or return an explicit, user-friendly conversion/compatibility error.

### CSV parser

- [x] Detect encoding and delimiter with safe fallbacks.
- [x] Extract headers and records while preserving row numbers.
- [x] Produce table-aware records with source file and exact row ranges.
- [x] Handle malformed rows and surface warnings without silently discarding data.

### PowerPoint parser

- [x] Extract slide number, title, text-bearing shapes, and tables from `.pptx` files.
- [x] Extract speaker notes when the selected library and file expose them; otherwise document the limitation.
- [x] Preserve slide number and title in normalized records.
- [x] Support `.ppt` or return an explicit, user-friendly conversion/compatibility error.

## 5. Structure-aware chunking

- [x] Create chunks that keep tables meaningful: include headers with data rows and chunk large tables by contiguous row ranges.
- [x] Chunk slide content per slide by default; split only oversized slides while retaining slide metadata.
- [x] Apply bounded chunk size and overlap only where free-form text needs it.
- [x] Ensure each chunk is human-readable, includes useful labels (for example sheet and headers), and preserves all source metadata.
- [x] Add tests covering small/large tables, missing headers, text-only slides, table slides, and mixed-document input.

## 6. Embeddings and vector index

- [x] Implement an embedding-provider interface and a configured provider implementation.
- [x] Batch embedding requests and handle rate limits, transient failures, and partial indexing failures.
- [x] Persist vector, chunk text, metadata, document fingerprint, and embedding-model/version information.
- [x] Implement idempotent indexing: reuse unchanged chunks and replace/remove obsolete chunks when a document changes. **Fixed (G3):** `LocalVectorStore.upsert` now deletes only the affected file's rows (`table.delete(file_name = ...)`) and adds the new ones, instead of reading the whole table and overwriting it. Document-level dedup via `has_document_id` is unchanged.
- [x] Provide a knowledge-base reset/delete operation only with an explicit confirmation path.

## 7. Retrieval and grounded answering

- [x] Embed each user question and retrieve configurable top-*k* relevant chunks across all indexed files.
- [x] Add a minimum relevance threshold and return no retrieved evidence below it.
- [x] Optionally add lightweight reranking or diversity controls to avoid returning near-duplicate chunks.
- [x] Construct an LLM prompt that restricts answers to retrieved context, asks it to identify uncertainty, and forbids invented facts/citations.
- [x] Implement deterministic no-answer behavior: when retrieval is weak or evidence is insufficient, state that the indexed documents do not provide enough information. **Fixed (G4):** `_is_llm_refusal` detects the model's refusal sentence and `RagService.answer` returns `is_no_answer=True` with no sources when it fires.
- [x] Return citations from retrieval metadata, including file name and sheet/row range or slide number/title.
- [x] Preserve and display the retrieved evidence separately from the generated answer for debugging/demo use.

## 8. Chatbot UI

- [x] Build an upload/indexing screen with accepted formats, index status, errors, and indexed-document list.
- [x] Build a chat screen that keeps question/answer history for the active session.
- [x] Show a concise answer followed by clickable or clearly formatted source references.
- [x] Add loading and failure states for upload, indexing, retrieval, and LLM calls.
- [x] Provide controls to view sources/retrieved chunks and to clear the active knowledge base.

## 9. Quality, safety, and demonstration

- [x] Create Acme Retail sample data: at least one spreadsheet, CSV, and presentation with deliberately cross-referenceable sales/target facts.
- [x] Write parser unit tests, including corrupt/unsupported files and metadata accuracy.
- [x] Write integration tests for upload -> extract -> chunk -> index -> retrieve, using deterministic/fake embeddings where needed.
- [x] Add end-to-end acceptance questions, including a multi-document question and an intentionally unanswerable question.
- [x] Verify citations against the source files manually for the demo dataset.
- [x] Document privacy/security assumptions, file retention, dependency/model limitations, and known legacy-format limitations.
- [x] Prepare a short demo script: upload files, index them, answer a single-source question, answer a multi-source question, show citations, and demonstrate no-answer behavior.

## Definition of done

- [x] A user can upload multiple valid Excel, CSV, and PowerPoint files in one session and see per-file indexing results.
- [x] Retrieved chunks retain correct source metadata from parsing through final answer citations.
- [x] The chatbot answers supported questions using evidence from one or more indexed documents and displays supporting locations.
- [x] The chatbot declines to answer when the indexed evidence is insufficient.
- [x] Corrupt and unsupported files fail safely with useful messages.
- [x] README, configuration instructions, tests, sample Acme Retail data, and the demo path are complete. **Fixed (G1, G6):** `.env` now loads for real; the stale future-integration sentence is removed and the faithfulness-gate fallback and provider-mismatch guard are documented.

## Gaps found in verification review (2026-09-03)

Ordered by impact. Each item names the file, the observed behavior, and the fix.

### G1 - `.env` is never read, so hosted mode cannot be switched on as documented

`src/config.py` reads `os.getenv` only. Nothing imports `python-dotenv` and `load_dotenv()` is never called, and `python-dotenv` is absent from `requirements.txt`. A user who follows `README.md` ("Copy `.env.example` to `.env` and configure `OPENAI_API_KEY` before starting the app") gets no key, no warning, and a silent fall back to hash embeddings. The System status panel then reports `Api Key Configured: False` with no explanation.

- [x] Add `python-dotenv` to `requirements.txt` and call `load_dotenv()` at the top of `src/config.py`. **Fixed.**
- [x] Add `EMBEDDING_DIMENSIONS` to `.env.example`; it is the only setting in `config.py` missing from that file. **Fixed.**

### G2 - Switching embedding providers silently corrupts retrieval scores

`_entry_for_lance` persists `embedding_model` but **nothing ever reads it back**. `cosine_similarity` in `src/embeddings.py` uses `zip`, which stops at the shorter vector. Indexing with the 256-dim hash provider and then querying with 1536-dim OpenAI embeddings returns a plausible-looking number rather than an error:

```
cosine_similarity([1.0]*256, [1.0]*1536) -> 256.0
```

Retrieval ranking becomes meaningless, and because scores far exceed `min_retrieval_score` the no-answer guard never fires. Adding an API key to a populated index is the exact path a demo would take.

- [x] Compare the stored `embedding_model` against the active provider on open; refuse to search a mismatched index and tell the user to re-index. **Fixed:** `LocalVectorStore.embedding_models()` plus mismatch checks in both `RagService.index_document` (raises `ValueError`) and `RagService.answer` (returns a clear `is_no_answer` response).
- [x] Raise in `cosine_similarity` when `len(left) != len(right)` instead of truncating. **Fixed** in `src/embeddings.py`.

### G3 - Indexing rewrites the entire table on every upload

`LocalVectorStore.upsert` loads all existing rows into memory, filters by `file_name`, then calls `create_table(..., mode="overwrite")`. Cost is O(total corpus) per file and every vector is rewritten, which contradicts the "avoid re-embedding unchanged documents" non-functional expectation at the chunk level. Document-level skipping via `has_document_id` does work; chunk-level reuse does not exist. There is also no atomicity: a crash mid-overwrite loses the whole knowledge base.

- [x] Use LanceDB `delete(where=...)` plus `add()` instead of a full-table overwrite. **Fixed** in `src/vector_store.py`.

### G4 - An LLM-emitted refusal is still reported as an answer with citations

`src/service.py:114` returns `is_no_answer=False` whenever any evidence survives filtering. The system prompt instructs the model to reply exactly `I can't answer that from the indexed documents.`, so in hosted mode that refusal is rendered as a normal answer with a Sources list under it — citations for a non-answer, which is precisely the grounding failure FR-08/FR-10 exist to prevent.

- [x] Detect the refusal sentinel in the generated text and set `is_no_answer=True` with empty `sources`. **Fixed** via `_is_llm_refusal` in `src/service.py`.

### G5 - The lexical AND-gate defeats semantic retrieval

`_has_lexical_overlap` (`src/service.py:168`) requires a literal shared token between question and chunk before a chunk can become evidence. It is a reasonable brake on hash embeddings, but it is applied unconditionally, so in OpenAI mode a correctly-retrieved chunk is discarded whenever the user paraphrases. "How did the southern territory perform?" cannot reach a chunk that says `Region: South`. This makes the system's recall no better than keyword search regardless of embedding quality.

- [x] Apply the overlap gate only when the hash provider is active, or demote it from a hard filter to a scoring signal. **Fixed:** `RagService.answer` now only applies `_has_lexical_overlap` when `isinstance(self.embeddings, HashEmbeddingProvider)`.

### G6 - README contradicts itself about OpenAI support

`README.md:28` says `OPENAI_API_KEY` "is reserved in `.env.example` for a **future** hosted embedding/LLM provider integration." `README.md:40` says the app "then uses OpenAI embeddings and a zero-temperature grounded-generation prompt." Both `OpenAIEmbeddingProvider` and `OpenAIAnswerGenerator` are implemented and wired in `RagService.__init__`. Line 28 is stale.

- [x] Delete the "future integration" sentence. **Fixed** in README.md.
- [x] Document the faithfulness gate: when `evaluate_faithfulness` rejects a generated answer, the app silently swaps in the extractive dump. Nothing in the README or UI tells the user this happened. **Fixed:** documented in README's Optional OpenAI mode section. UI-level surfacing (a caption when the fallback fires) is still not implemented; the app logs it but does not display it in `app.py`.

### G7 - The default no-key demo path does not produce a "concise answer"

Section 8 of the use case asks for a concise answer followed by sources. Without an API key - the default, and the path `DEMO.md` walks through - `_extractive_answer` returns the first two chunks concatenated verbatim:

```
Based on the indexed evidence: Sheet: Regional Sales Region: South | Q1 Revenue: 4200000 | Q1 Target: 4000000 | ...
```

Citations and grounding are correct, but this is a retrieval dump, not an answer. The stated deliverable is only fully met when a key is configured, and G1 currently blocks configuring one.

- [x] Either state plainly in `README.md`/`DEMO.md` that concise prose requires `OPENAI_API_KEY`, or add a small deterministic answer formatter for the fallback. **Fixed via documentation**, not a formatter: synthesizing genuinely concise prose without an LLM risks restructuring facts beyond what is literally in the chunk, which is the opposite of the grounding requirement. README's Optional OpenAI mode section now says the no-key fallback returns evidence verbatim, not prose.

### G8 - Chunker silently drops records that share a slide

`chunk_records` groups by `(document_id, sheet_name, slide_number)` and then uses only `group_records[0]` for slide groups (`src/chunking.py:25`), discarding every other record in the group. Confirmed:

```
two ExtractedRecords, same slide_number -> 1 chunk, second record's text absent
```

Currently masked because `parse_powerpoint` emits exactly one record per slide. Any future split of slide parsing loses data with no error.

- [x] Chunk the concatenation of the group rather than its first element. **Fixed** in `src/chunking.py`; regression test `test_slide_group_with_multiple_records_keeps_every_record` added.

### G9 - Smaller correctness and hygiene items

- [x] `data/app.log` is not in `.gitignore` (only `data/uploads/` and `data/lance/` are). The log records question text and file names, so it would be committed. `data/uploads/` is listed but never created - uploads are processed in memory. **Fixed:** added `data/*.log` to `.gitignore`.
- [x] `parse_powerpoint` reads `slide.notes_slide` without checking `slide.has_notes_slide`; python-pptx creates a notes slide as a side effect. Guard it. **Fixed** in `src/parsers.py`.
- [x] `chunk_records` defaults to `rows_per_chunk=8` while `Settings.chunk_rows` defaults to `6`. Two defaults for one knob; direct calls in tests and the service disagree. **Fixed:** default aligned to `6`.
- [x] `parse_excel` loads the workbook twice and walks every cell of every sheet a second time purely to detect stale formulas. Quadratic-feeling on real workbooks; collect formulas in the single pass that already reads the rows. **Fixed:** headers, data rows, and formula warnings are now collected in one zipped pass over `worksheet`/`formula_worksheet`. The two `load_workbook` calls (data_only vs formula view) remain, since openpyxl cannot expose cached values and formula text from a single loaded workbook.
- [x] No test exercises `OpenAIEmbeddingProvider` or `OpenAIAnswerGenerator`. Both are untested network code on the path an interviewer is most likely to enable. Add tests with a stubbed transport. **Fixed:** `test_openai_embedding_provider_parses_response_back_into_request_order` and `test_openai_answer_generator_sends_grounded_prompt_and_parses_reply` patch `urllib.request.urlopen`.
- [x] `.xls` and `.ppt` are accepted by the uploader and the parser only to produce a conversion error. That is a deliberate, documented choice, but the use case lists both as input formats - worth stating as a scoped limitation rather than a checked capability. **Left as-is by design**, already stated plainly in README.md's opening bullets and DEMO.md; no code change needed here.
