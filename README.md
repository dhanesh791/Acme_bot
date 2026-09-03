# Acme Retail Multi-Format RAG Chatbot

A small interview prototype for asking grounded questions across CSV, Excel, and PowerPoint files.

## What it does

- Upload and index `.csv`, `.xlsx`, and `.pptx` documents.
- Preserve source metadata: file, CSV row, Excel sheet/row range, and PowerPoint slide/title.
- Retrieve matching chunks using deterministic local hash embeddings and return only retrieved evidence.
- Show citations and inspect the exact retrieved chunks in the chat UI.
- Decline questions that lack relevant indexed evidence.

Legacy `.xls` and `.ppt` files are detected but intentionally require conversion to modern formats for this prototype. PowerPoint speaker notes are extracted when present and exposed by the library.

## Run it

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local address Streamlit prints. Upload the three files in `sample_data/`, click **Index uploaded files**, then ask: `What was South region's Q1 revenue and target attainment?`

## Design

`src/parsers.py` converts each format into normalized records. `src/chunking.py` creates table-aware row-range chunks or slide chunks while retaining their source metadata. `src/vector_store.py` persists vectors and metadata locally in LanceDB under `data/lance/`; `src/service.py` retrieves evidence and produces the grounded response.

The default deterministic embedding and extractive response modes do not require an API key, making the demo reliable offline. Setting `OPENAI_API_KEY` (see **Optional OpenAI mode** below) switches both embeddings and answer generation to OpenAI; the app refuses to mix embedding models in one knowledge base, so switch providers by clearing the knowledge base first, not mid-session.

### Metadata and storage

Rows and slides use one-based positions. CSV and Excel citations show `file -> sheet (when present) -> row N-M`; PowerPoint citations show `file -> Slide N (title)`. Metadata remains attached to each LanceDB vector and can filter retrieval by file, format, sheet, or slide.

Each browser session receives its own LanceDB namespace under `data/lance/`; clearing the knowledge base deletes only that session's namespace. Uploaded bytes are processed in memory and are not retained by the application. Local index files and logs are excluded from Git. This prototype has no authentication, so it should not be exposed as a shared public deployment.

The browser session is the access boundary. Session indexes are automatically removed after 24 hours by default (`SESSION_RETENTION_HOURS` configures this). In a real deployment, authenticate users, associate each namespace with an account/tenant, encrypt storage, and run retention cleanup as a scheduled job. Do not place sensitive documents in a publicly reachable instance.

### Optional OpenAI mode

Copy `.env.example` to `.env` and configure `OPENAI_API_KEY` before starting the app (`.env` is loaded automatically via `python-dotenv`). The app then uses OpenAI embeddings and a zero-temperature grounded-generation prompt. Without a key it uses local hash embeddings and returns retrieved evidence verbatim as the answer, which is grounded but not prose.

A generated answer is only shown if it passes a deterministic faithfulness check (`src/evaluation.py`) against the retrieved evidence and is not itself a refusal; otherwise the app logs a warning and falls back to the extractive answer. An existing knowledge base remembers which embedding model indexed it (`embedding_model` per chunk); indexing or asking questions with a different provider is refused with a message to clear the knowledge base first, rather than silently corrupting retrieval scores.

## Validation

```powershell
python -m pytest -q
```

The tests cover CSV metadata, chunk row ranges, unsupported/legacy errors, retrieval with citations, no-answer behavior, embedding-model mismatch guards, and stubbed OpenAI embedding/generation calls.

If pytest fails with a Windows `PermissionError`/`WinError 5` under a long path (common when the project lives inside OneDrive), it is a `tmp_path`/LanceDB `MAX_PATH` issue, not a code failure. Point pytest at a short base directory instead:

```powershell
python -m pytest -q --basetemp=C:\pt
```
