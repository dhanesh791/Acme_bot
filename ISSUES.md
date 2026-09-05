# Issues Log

Two things in one place: a quick reference for enabling OpenAI mode, and a running
summary of every problem hit while building this RAG chatbot, condensed to one point
each with its fix. Full technical detail for anything below lives in `tasks.md`.

## Quick reference: enabling OpenAI mode

1. `copy .env.example .env` (in the project root; `.env` is gitignored, local only).
2. Set `OPENAI_API_KEY=sk-...` in `.env`.
3. Restart the app (`streamlit run app.py`) — `.env` loads once at startup, not per request.
4. Confirm in the sidebar's **System status**: `Api Key Configured: True`, `Answer Mode: OpenAI grounded generation`.
5. If documents were already indexed under a different provider this session, clear the knowledge base first — the app refuses to mix embedding models in one index.

## Problems encountered, and how they were fixed

### Verification review pass (found by reading the code end to end, before trusting the existing checklist)

- **`.env` was never loaded.** `config.py` read `os.getenv` directly with no `load_dotenv()` call. → Added `python-dotenv`, load it before `Settings` reads anything.
- **Switching embedding providers silently corrupted retrieval scores.** `cosine_similarity` used `zip()`, which truncates instead of erroring on a dimension mismatch. → Raise on mismatch; block indexing/querying with a different provider than what's already stored.
- **Every document upload rewrote the entire vector table.** O(whole corpus) per file, no atomicity. → Targeted `delete()` + `add()` instead of full overwrite.
- **An LLM refusal was rendered as a cited answer.** The model's own "I can't answer..." text came back with a Sources list under it. → Detect the refusal sentinel, route it to the no-answer path.
- **The lexical-overlap safety gate defeated real semantic search in OpenAI mode.** A paraphrased question with no literal shared word couldn't retrieve a correct chunk. → Gated the check to only apply when the local hash provider is active.
- **The chunker silently dropped data.** Grouping by slide/section only ever chunked the first record in a group. → Combine the whole group before chunking.
- **README contradicted itself** about whether OpenAI support existed. → Removed the stale "future integration" line.
- **The no-key answer isn't "concise" prose**, just retrieved evidence verbatim. → Documented as an intentional trade-off rather than synthesizing further, which would risk inventing structure not literally in the data.
- **Several smaller gaps**: `app.log` not gitignored, a PPTX-notes-slide read with a write side effect, a chunk-size default that didn't match its own config, `parse_excel` reading the workbook twice, no tests for the OpenAI provider classes. → Fixed individually; see `tasks.md` for each.

### Adding Word (`.docx`) support

- **New sample data broke an unrelated, already-passing test.** The new sample memo's prose happened to contain the word "Acme," which gave the existing no-answer test ("What is Acme's vacation policy?") accidental lexical overlap with real indexed content. → Reworded the question to share zero tokens with the corpus.

### Rebuilding retrieval as a full RAG-standard pipeline (hybrid search + reranking + MMR)

- **Removing the old lexical-overlap gate broke the no-answer test again — for a different reason than expected.** The hash embedding provider was found to produce a genuine 0.29 cosine "similarity" between an unrelated question and an unrelated chunk, purely from hash collisions in its 256-dimension space. → Reinstated the gate, scoped to the hash provider only (hybrid BM25 already covers real lexical matching for other providers).
- **A real embedding model produced the same kind of false positive — and only live testing caught it, not the unit suite.** `bge-small-en-v1.5` scored 0.52 cosine between an unrelated question and an unrelated chunk; short "Field: value" table-row text just doesn't give it much to discriminate on. The cross-encoder reranker scored the identical pair -11.4. → Made reranking a second no-answer gate (`min_rerank_score`), not just a reordering step.
- **Playwright's fixed-timeout waits silently broke once the app's real latency stopped being near-instant.** `waitForSelector(sel, {state:'detached'})` resolves immediately if the element is never seen attached at all. → Switched to polling for a result marker's count to increase, with a generous timeout, instead of guessing a delay.

### Found independently, after handoff

- **`MIN_RERANK_SCORE=0.0` was too strict and rejected a genuinely correct answer.** A relevant chunk scored -2.41 under the cross-encoder; the initial threshold treated any negative score as irrelevant. → Recalibrated to `-6.0` (real irrelevance scores around -11), added a regression test.
- **The local ONNX models defaulted to caching in the OS Temp directory**, which Windows or a cleanup tool can silently clear, forcing a surprise ~150MB re-download. → Pointed the cache at `data/model_cache/`, the same stable location already used for the vector index and logs.
- **The faithfulness-gate fallback was invisible to the user.** When a generated answer failed the groundedness check, the extractive fallback was shown with no indication anything had gone differently — only the log recorded it. → Added a `used_extractive_fallback` flag and a small UI notice.

### Development/tooling problems (not application bugs)

- **Windows `MAX_PATH` broke pytest under this machine's long OneDrive path.** Not a code defect. → Documented the `--basetemp=<short path>` workaround in the README.
- **Piping generated code through a Bash heredoc into a Python string literal corrupted the output, twice** — escape sequences meant to survive shell quoting didn't survive being nested inside a Python triple-quoted string too. → Stopped doing that for substantial content; used the Write/Edit tools directly instead.
- **Streamlit's `st.selectbox` turned out to be a React Aria `ComboBox`, not a plain dropdown** — automating it by clicking and looking for a static option list found nothing. → Click the actual input, `.fill()` to filter, `Enter` to commit.
- **Playwright's `hasText` filter only matches rendered text, not an `<input>`'s current value.** Re-finding a selectbox by its just-set value returned nothing. → Always filter by the fixed label instead.
- **A stale `streamlit run` process from an earlier session was still holding the port,** and `lsof` (the usual way to find/kill it) isn't available in this environment. → Found the real PID via a PowerShell `Get-CimInstance` query, cross-checking `CommandLine` among several look-alike wrapper processes.
