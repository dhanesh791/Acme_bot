# Problems and Bugs Encountered

A record of real issues hit while building, reviewing, and extending this project —
both bugs in the application and problems in the tooling used to build/test it.
Written after the fact from the actual session, not a generic checklist.

## Application bugs found by the verification review pass (2026-09-03)

`tasks.md` had every box checked before this pass; reading the code end to end and
running it surfaced nine real gaps (G1–G9 in `tasks.md`). The most serious:

1. **`.env` was never loaded.** `src/config.py` read `os.getenv` directly; nothing
   called `load_dotenv()`. Following the README's own setup steps (`cp .env.example
   .env`, set `OPENAI_API_KEY`) did nothing — silent fallback to local mode with no
   warning. Fixed by adding `python-dotenv` and calling `load_dotenv()` before
   `Settings` reads any variable.
2. **Switching embedding providers silently corrupted retrieval.** `cosine_similarity`
   used `zip()`, which truncates on length mismatch instead of erroring —
   `cosine_similarity([1.0]*256, [1.0]*1536)` returned `256.0` with no complaint.
   Add an API key to an already-indexed knowledge base and every similarity score
   becomes meaningless while looking plausible. Fixed by raising on length mismatch
   and adding an explicit stored-embedding-model check on both index and query paths.
3. **Every document upload rewrote the entire vector table.** `LocalVectorStore.upsert`
   read all existing rows into memory and called `create_table(mode="overwrite")` —
   O(whole corpus) per file, and no atomicity (a crash mid-write loses everything).
   Fixed with targeted `table.delete(where=...)` + `table.add()`.
4. **An LLM refusal was rendered as a cited answer.** The system prompt told the model
   to reply `"I can't answer that from the indexed documents."` on insufficient
   context, but `RagService.answer` unconditionally set `is_no_answer=False` whenever
   any evidence survived filtering — so the refusal string came back with a Sources
   list under it. Fixed by detecting the refusal sentinel and routing it to the same
   no-answer path as weak retrieval.
5. **The lexical-overlap safety gate defeated semantic search in hosted mode.**
   `_has_lexical_overlap` — a reasonable guard for the crude local hash embeddings —
   was applied unconditionally, so a paraphrased question with no literal shared word
   couldn't retrieve a correct chunk even with real OpenAI embeddings. Fixed by gating
   it on `isinstance(self.embeddings, HashEmbeddingProvider)`.
6. **The chunker silently dropped data.** `chunk_records` grouped slide-style records
   by `(document_id, sheet_name, slide_number)` and then only chunked
   `group_records[0]` — any second record sharing a slide/section key vanished with no
   error. Not yet triggered by the shipped parsers (each emits one record per slide),
   but a real trap for the next parser change. Fixed by combining the whole group.
7. **README contradicted itself.** One paragraph called OpenAI support "reserved for
   a future integration"; another paragraph two sections down described using it.
   Both `OpenAIEmbeddingProvider` and `OpenAIAnswerGenerator` were already implemented
   and wired up — the "future" line was just stale.

Full list with file/line detail: `tasks.md`, "Gaps found in verification review."

## Application bug found while adding Word support

8. **New sample data broke an unrelated passing test via word overlap.** Adding
   `q1_summary_memo.docx` (whose prose starts "**Acme** Retail delivered...") gave the
   existing no-answer acceptance test — `"What is Acme's vacation policy?"` — an
   accidental shared token with newly-indexed content. Under the hash-embedding +
   lexical-overlap gate, that was enough to pull in evidence and return an answer
   instead of refusing, silently breaking the test's actual intent (verifying refusal
   on genuinely absent information, not on zero-token-overlap by accident). Caught by
   running the full suite after the change, not by inspection. Fixed by rewording the
   question (and the matching DEMO.md step) to `"What is the employee vacation
   policy?"`, which shares no tokens with any indexed content.
   **Lesson:** an intentionally-unanswerable test question is only as robust as its
   vocabulary distance from the corpus — adding sample data can quietly erode that
   distance without touching the test file itself.

## Two application bugs found while rebuilding retrieval as a full RAG pipeline

Asked directly "what methods are we using, I want the best method possible," and
given the go-ahead for the full option: real local embeddings (`fastembed`), hybrid
dense+BM25 retrieval, cross-encoder reranking, MMR diversity. Rebuilding the no-answer
gate around this new pipeline surfaced two real bugs — one from the unit suite, one
that only live browser verification caught.

9. **Removing the old lexical-overlap gate broke the no-answer test, again — but not
   for the reason assumed.** The gate looked redundant once hybrid BM25 retrieval was
   in place (BM25 already handles lexical matching), so it was deleted outright.
   `test_service_refuses_without_evidence` immediately failed. Investigated instead of
   reverting blind: the hash embedding provider was confirmed to produce a genuine
   **0.29 cosine "similarity"** between `"What is the employee vacation policy?"` and
   an unrelated indexed row — purely from hash collisions in its 256-dimension hashed
   bag-of-words space, comfortably above the 0.12 threshold. The gate had been doing
   two *different* jobs the whole time: enabling lexical matching (which hybrid BM25
   does genuinely supersede) and suppressing hash-collision false positives (which it
   does not). Reinstated, scoped to the hash provider only.
10. **The same failure mode reappeared with a real embedding model, and only live
    verification caught it — the unit suite runs on the hash provider by design and
    never exercises this path.** Driving the actual Streamlit app with Playwright
    against the real pipeline, the identical no-answer question — this time with a
    genuine semantic embedding model (`bge-small-en-v1.5`), not hash collisions —
    still returned an answer instead of refusing. Measured directly: **0.52 cosine
    similarity** between that question and an unrelated retention-data row. Not a
    collision artifact this time — short, telegraphic "`Field: value | Field: value`"
    table-row text just doesn't give a general-purpose sentence embedding much to
    discriminate on. The cross-encoder reranker scored the identical pair **-11.4** —
    correctly and decisively irrelevant. Fix: reranking became a second no-answer gate
    (`min_rerank_score`), not just a reordering step, for any provider a real reranker
    actually ran against.
    **Lesson:** a fast, hermetic unit suite that deliberately runs on a synthetic
    embedding provider (for good reasons — speed, determinism, no network) will never
    catch a failure mode that only exists in the real provider's embedding geometry.
    That gap is exactly what live, real-pipeline verification is for — this bug shipped
    invisibly through 48 passing unit tests and was only caught by actually using the
    app.

## Development/tooling problems (not application bugs)

These didn't ship in the product but cost real time during the session and are worth
recording so they don't get re-discovered from scratch next time.

- **Windows `MAX_PATH` breaks pytest under a long OneDrive path.** Plain
  `python -m pytest -q` failed 11 of 26 tests with `PermissionError [WinError 5]`
  because `tmp_path` fixtures landed under
  `C:\Users\<user>\OneDrive\Desktop\Acme_bot\...`, pushing LanceDB's file paths past
  Windows' 260-character limit. Not a code defect — running the same suite with
  `--basetemp=C:\pt` (a short path) passed cleanly. Documented in the README's
  Validation section so it isn't mistaken for a real failure next time.
- **Piping generated code through Bash heredoc → Python string literal → file write
  corrupted the output twice.** Editing `src/chunking.py` and later rewriting
  `tests/test_pipeline.py` via `python - <<'PY' ... PY` heredocs with embedded `\n`
  escapes produced files with literal, unintended line breaks in the middle of string
  literals (`SyntaxError: unterminated string literal`) — the escaping meant to
  survive shell quoting didn't survive consistently once nested inside a Python
  triple-quoted string inside a heredoc. Fixed by abandoning that path entirely for
  substantial content and using the `Write`/`Edit` tools directly (no shell
  intermediary) instead. **Lesson:** for anything beyond a one-line `sed`-style
  substitution, skip the heredoc-generates-Python-generates-file chain — write the
  target file directly.
- **Streamlit's `st.selectbox` here is a React Aria `ComboBox`, not a plain
  dropdown.** It renders as a filterable `<input role="combobox">` with a separate
  hidden "Open" button, not a clickable box that reveals a static option list.
  Automating it by clicking the widget and then `getByRole('option', {name: ...})`
  silently found zero options (the click landed on the outer container/label, not the
  input, and no popup ever opened). Diagnosed by dumping the widget's `innerHTML`.
  Fixed by clicking the actual `getByRole('combobox')` input, `.fill()`-ing the target
  option text to filter the list, then pressing `Enter` to commit it.
- **Playwright's `locator(...).filter({ hasText })` only matches rendered text nodes,
  not an `<input>` element's `value` attribute.** After changing a selectbox's value,
  trying to re-find that same selectbox via `hasText: '<the new value>'` returned zero
  elements — the value lives in an attribute, not the DOM's visible text content, so
  `hasText` never sees it. Only the static `<label>` text is a reliable anchor. Fixed
  by always filtering selectboxes by their fixed label ("Word section"), never by
  their current value.
- **A stale `streamlit run app.py` process from an earlier session was still holding
  port 8501,** serving old code while a fresh background launch failed with `Port 8501
  is not available`. `lsof`, the tool the run-skill's own pattern assumes for freeing
  a port, isn't available in this Git Bash environment, so that standard "find and
  kill the port's listener" one-liner didn't work as documented. Had to fall back to
  `Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%streamlit run app.py%'"`
  via PowerShell — which itself returned several *wrapper* `bash.exe` processes
  running the launch command as a string, alongside the one real `python.exe`
  process actually holding the socket — and cross-check `CommandLine` per PID to find
  the right one to kill.
- **Fixed-timeout Playwright waits silently broke once the app's real latency changed.**
  The browser-automation driver's wait logic (`waitForSelector(spinner, {state:
  'detached'})` plus a short fixed delay) worked fine against the instant hash-embedding
  pipeline, then started producing screenshots of *empty, still-loading* chat turns once
  real local model inference added real latency (~1-3s cold, sub-second warm). Root
  cause: `waitForSelector(sel, {state: 'detached'})` resolves *immediately* if the
  selector is never seen attached at all — it does not wait for a genuinely-appearing
  element to later disappear, it's trivially satisfied by absence. A short fixed pre-wait
  plus that pattern is a race condition waiting for the backend to become slow enough to
  expose it. Fixed by waiting on a state-based signal instead: poll for the count of a
  marker that only exists once a turn is actually fully rendered (here, the "Retrieved
  evidence" expander) to increase, with a generous timeout, rather than guessing a delay.
  **Lesson:** a browser-automation wait tuned against a fast backend can pass cleanly for
  a long time and then fail the moment the backend gets slower — treat "wait for spinner
  gone" as inherently racy and wait for the actual result to appear instead.
