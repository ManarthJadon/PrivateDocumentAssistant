# Private Document Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **How this project uses the plan:** the user builds every task themselves, one step at a
> time. Claude gives the full code for each step in chat when that step starts. This file
> pins the decisions: files, names, signatures, exact values and tests.

**Goal:** A fully local RAG web app: workspaces, document upload, questions answered with sources.

**Architecture:** FastAPI app on 127.0.0.1 talks to Ollama on Windows (embeddings + answers) and
to Postgres + pgvector in Docker (127.0.0.1:5433). Plain SQL in `app/db.py`, no ORM, no LangChain.

**Tech Stack:** Python 3.14, uv, FastAPI, uvicorn, psycopg 3, pgvector, pypdf, python-docx,
python-multipart, httpx, python-dotenv, pytest; plain HTML/CSS/JS.

**Spec:** `docs/superpowers/specs/2026-10-19-private-document-assistant-design.md`

## Global Constraints
- Python 3.14; install with `uv pip install` (never `uv add`); `requirements.txt` from `uv pip compile pyproject.toml -o requirements.txt --universal`
- Postgres at `127.0.0.1:5433`; tests use the database `docassistant_test` only
- Models: `nomic-embed-text` (vectors of 768), `llama3.1:8b`; `num_ctx` 8192; temperature 0.1; Ollama timeout 120 s
- Embedding prefixes: `search_document: ` for chunks, `search_query: ` for questions
- Chunks ~1000 characters, overlap 150; top 5; exact search, no vector index
- Uploads max 20 MB; types `.pdf`, `.docx`, `.txt`, `.md`
- All SQL lives in `app/db.py`
- The app listens only on `127.0.0.1`
- User-facing messages are exactly as in spec section 8; never show raw errors
- Commits have no Claude attribution; push straight to `main`

## Review Focus
1. Workspace names that differ only in case ("College" / "college") count as duplicates → Task 4
2. Upper-case extensions ("NOTES.PDF") are accepted → Task 3
3. Filenames carrying folders ("C:\fakepath\notes.pdf", "../../evil.txt") keep only the last part → Task 6
4. HTML inside documents (`<script>`) shows as plain text on the page, never runs → Task 10
5. A "word" longer than a chunk (a long URL, text with no spaces) still gets chunked, no endless loop → Task 2

---

### Task 1: Project setup and settings
**Files:** Create `pyproject.toml`, `requirements.txt` (generated), `app/__init__.py` (empty), `app/config.py`, `tests/test_config.py`

**Produces:**
- `@dataclass(frozen=True) Settings`: `db_conninfo: str`, `ollama_url: str`, `embed_model: str`, `chat_model: str`, `uploads_dir: Path`
- `get_settings() -> Settings`: calls `load_dotenv()` (never overrides existing env vars) and reads env on every call. Keys and defaults: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`=`127.0.0.1`, `POSTGRES_PORT`=`5433`, `OLLAMA_URL`=`http://localhost:11434`, `EMBED_MODEL`=`nomic-embed-text`, `CHAT_MODEL`=`llama3.1:8b`, `UPLOADS_DIR`=`uploads`. `db_conninfo` is built with `psycopg.conninfo.make_conninfo(...)`.

- [ ] `pyproject.toml`: dependencies above, `[dependency-groups] dev = ["pytest"]`, `[tool.pytest.ini_options] pythonpath = ["."]`, `testpaths = ["tests"]`
- [ ] Run `uv venv`, then `uv pip install -r pyproject.toml --group dev`. Expected: no errors. If a package fails on 3.14, stop (spec fix 6)
- [ ] Generate `requirements.txt`
- [ ] Test `test_get_settings_reads_env`: with env `POSTGRES_DB=x`, `POSTGRES_PORT=5999`, `UPLOADS_DIR=tmpdir` and `CHAT_MODEL` unset → `"dbname=x"` and `"port=5999"` in `db_conninfo`, `uploads_dir == Path("tmpdir")`, `chat_model == "llama3.1:8b"`
- [ ] Run it (FAIL) → write `config.py` → run it (PASS) → commit `chore: project setup and settings`

### Task 2: Chunker + GitHub Actions
**Files:** Create `app/chunker.py`, `tests/test_chunker.py`, `.github/workflows/tests.yml`

**Produces:** `CHUNK_SIZE = 1000`, `CHUNK_OVERLAP = 150`; `@dataclass Chunk(page: int | None, text: str)`;
`split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]`;
`chunk_pages(pages: list[tuple[int | None, str]]) -> list[Chunk]` (splits each page separately, keeps its page)

Algorithm for `split_text`:
```
start = 0
while start < len(text):
    end = min(start + size, len(text))
    if end < len(text):
        for sep in ("\n\n", ". ", " "):            # paragraph, then sentence, then word
            cut = text.rfind(sep, start + size // 2, end)
            if cut != -1:
                end = cut + len(sep)
                break                               # no sep found: hard cut at end
    piece = text[start:end].strip()
    if piece: add piece
    if end >= len(text): stop
    space = text.find(" ", end - overlap, end)      # next chunk starts at a word start
    start = max(space + 1 if space != -1 else end, start + 1)
```

Tests:
- [ ] `test_empty_text_gives_no_chunks`: `split_text("   ") == []`
- [ ] `test_short_text_is_one_chunk`: `split_text("Hello world.") == ["Hello world."]`
- [ ] `test_chunks_respect_size`: `"word " * 1000` → every chunk `len <= 1000`
- [ ] `test_never_cuts_mid_word`: `" ".join(f"w{i}" for i in range(2000))` → every word of every chunk is an original word
- [ ] `test_overlap_repeats_text`: same text → `chunks[i][-50:].strip() in chunks[i + 1]`
- [ ] `test_prefers_paragraph_break`: `"a " * 350 + "\n\n" + "b " * 350` → first chunk has no `"b"`
- [ ] `test_long_word_is_hard_cut`: `"x" * 2500` → returns, `len >= 3`, every chunk `len <= 1000` (Review Focus 5)
- [ ] `test_chunk_pages_never_crosses_pages`: pages `(1, "apple " * 300)`, `(2, "banana " * 300)` → page-1 chunks have no "banana", page-2 chunks no "apple", pages seen `{1, 2}`
- [ ] `test_chunk_pages_keeps_none_page`: `[(None, "hi there")] → [Chunk(None, "hi there")]`
- [ ] Run (FAIL) → implement → run (PASS)
- [ ] Workflow: on push to `main`; ubuntu-latest; checkout, setup-python `3.14`, setup-uv (action versions checked when the step starts); `uv venv`; `uv pip install -r pyproject.toml --group dev`; `.venv/bin/pytest -v`
- [ ] Commit `feat: chunker and CI`, push. Check: the GitHub Actions tab shows green

### Task 3: Reader
**Files:** Create `app/reader.py`, `tests/test_reader.py`, `tests/fixtures/sample.pdf`, `tests/fixtures/sample.docx`

**Produces:** `SUPPORTED_TYPES = {".pdf", ".docx", ".txt", ".md"}`; `class ReadError(Exception)` (its text is the user message);
`read_document(filename: str, data: bytes) -> list[tuple[int | None, str]]`
- Type from `Path(filename).suffix.lower()`; otherwise "Only .pdf, .docx, .txt and .md files are supported."
- PDF: `pypdf.PdfReader(io.BytesIO(data))`, one tuple per page numbered from 1; encrypted or any pypdf error → "Couldn't read this file. It may be damaged or locked."
- DOCX: `docx.Document(io.BytesIO(data))`, paragraphs joined with `"\n\n"`, page `None`; error → same message
- TXT/MD: `data.decode("utf-8-sig", errors="replace")`, page `None`
- All text blank → "No text found. Scanned PDFs aren't supported yet."

Fixtures (made by the user in Word): `sample.pdf` = page 1 "Apples are red.", page break, page 2 "Bananas are yellow." (Save as PDF); `sample.docx` = "Cherries are dark red."

Tests:
- [ ] `test_pdf_pages_are_numbered`: `(1, …"Apples"…)`, `(2, …"Bananas"…)`
- [ ] `test_docx_has_no_page`: one tuple, page `None`, contains "Cherries"
- [ ] `test_txt_and_md`: `read_document("a.txt", b"Hello") == [(None, "Hello")]`, same for `.md`
- [ ] `test_uppercase_extension_works`: `"NOTES.TXT"` (Review Focus 2)
- [ ] `test_non_utf8_text_does_not_crash`: `"café".encode("cp1252")` → contains "caf"
- [ ] `test_blank_pdf_raises_no_text`: blank page from `pypdf.PdfWriter().add_blank_page(width=200, height=200)`
- [ ] `test_empty_txt_raises_no_text`: `b"   "`
- [ ] `test_unsupported_type`: `"a.exe"`
- [ ] `test_broken_pdf`: `b"not a pdf"` → the "Couldn't read" message
- [ ] Run (FAIL) → implement → run (PASS) → commit `feat: read pdf, docx, txt and md`

### Task 4: Database basics + workspaces
**Files:** Create `app/db.py`, `tests/conftest.py`, `tests/test_db.py`; modify `.github/workflows/tests.yml`

**Produces:**
- `class NotFound(Exception)` (text "Not found."), `class AlreadyExists(Exception)` (text = user message)
- `connect(conninfo: str) -> psycopg.Connection`: `autocommit=True`, `row_factory=dict_row`, runs `CREATE EXTENSION IF NOT EXISTS vector`, then `register_vector(conn)`. Multi-step writes use `with conn.transaction():`
- `init_db(conn) -> None`: creates the tables if missing:
  - `workspaces(id bigint generated always as identity primary key, name text not null, created_at timestamptz not null default now())` + `CREATE UNIQUE INDEX IF NOT EXISTS workspaces_name_lower ON workspaces (lower(name))`
  - `documents(id …, workspace_id bigint not null references workspaces on delete cascade, filename text not null, stored_path text not null, page_count int not null, created_at …, unique (workspace_id, filename))`
  - `chunks(id …, document_id bigint not null references documents on delete cascade, page int, text text not null, embedding vector(768) not null)`
- `create_workspace(conn, name: str) -> int`: a unique violation becomes `AlreadyExists("A workspace called {name} already exists.")`
- `list_workspaces(conn) -> list[dict]` (id, name; ordered by name); `get_workspace(conn, workspace_id: int) -> dict | None`

Steps:
- [ ] One time: `docker compose exec db createdb -U docassistant docassistant_test`
- [ ] `conftest.py`: sets `os.environ["POSTGRES_DB"] = "docassistant_test"` at import. Fixture `conn`: refuses to run unless `"dbname=docassistant_test"` is in the conninfo; connects; `DROP TABLE IF EXISTS chunks, documents, workspaces`; `init_db`; yields; closes
- [ ] Tests: `test_init_db_twice_is_safe`; `test_create_and_list_workspaces` (names `["College", "Home"]`); `test_duplicate_name_raises`; `test_name_differing_only_in_case_is_duplicate` (Review Focus 1); `test_get_missing_workspace_returns_none`
- [ ] Run (FAIL) → implement → run (PASS)
- [ ] CI: service `pgvector/pgvector:pg17` with `POSTGRES_USER=docassistant`, `POSTGRES_PASSWORD=ci-only-password`, `POSTGRES_DB=docassistant_test`, port `5433:5432`, `pg_isready` health check; same values as job env plus `POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=5433`
- [ ] Commit `feat: database tables and workspaces`, push. Check: Actions green

### Task 5: Ollama client (embeddings) + fake Ollama
**Files:** Create `app/ollama_client.py`, `tests/fakes.py`, `tests/test_ollama_client.py`, `context/check_embed.py` (gitignored)

**Produces:**
- `class OllamaError(Exception)` and its subclasses: `OllamaUnavailable` ("Ollama isn't running. Start it and try again."), `ModelMissing(model)` ("Model {model} not found. Run: ollama pull {model}"), `OllamaTimeout` ("The AI took too long. Try again.")
- `EMBED_BATCH = 32`
- `OllamaClient(base_url: str, embed_model: str, chat_model: str, timeout: float = 120.0, transport: httpx.BaseTransport | None = None)`
  - `embed_documents(texts: list[str]) -> list[list[float]]`: POST `/api/embed` `{"model", "input": ["search_document: " + t, …]}` in batches of 32; reads `"embeddings"`
  - `embed_query(text: str) -> list[float]`: same with `"search_query: "`
  - `httpx.ConnectError` → `OllamaUnavailable`; `httpx.TimeoutException` → `OllamaTimeout`; HTTP 404 → `ModelMissing`
- `tests/fakes.py` `FakeOllama`: same methods plus `chat(system: str, user: str) -> str`; attributes `reply = "Fake answer [1]."`, `fail_after: int | None = None` (raises `OllamaUnavailable` once more texts than that were embedded in total), `down = False` (every call raises `OllamaUnavailable`), counters `embed_calls`, `chat_calls`, `last_user_prompt`. Vectors: 768 floats, `v[0] = 0.1`, then for each lower-case word `v[zlib.crc32(word) % 767 + 1] += 1` (texts sharing words are close)

Tests (`httpx.MockTransport`):
- [ ] `test_embed_documents_adds_prefix_and_batches`: 40 texts → 2 requests; first input is `"search_document: t0"`; 40 vectors back
- [ ] `test_embed_query_adds_prefix`
- [ ] `test_connection_error_raises_unavailable`; `test_timeout_raises_timeout`
- [ ] `test_404_raises_model_missing`: text is `"Model nomic-embed-text not found. Run: ollama pull nomic-embed-text"`
- [ ] `test_fake_similar_texts_are_closer`: fake cosine("apples are red", "red apples") < cosine("apples are red", "stock market")
- [ ] Run (FAIL) → implement → run (PASS)
- [ ] Check with real Ollama: `python context/check_embed.py` prints `768`
- [ ] Commit `feat: ollama embeddings and fake ollama`

### Task 6: Adding a document
**Files:** Create `app/ingest.py`, `tests/test_ingest.py`, `context/try_add.py`; modify `app/db.py`

**Produces (db):** `document_exists(conn, workspace_id: int, filename: str) -> bool`;
`insert_document(conn, workspace_id: int, filename: str, stored_path: str, page_count: int) -> int`;
`insert_chunks(conn, document_id: int, chunks: list[Chunk], embeddings: list[list[float]]) -> None` (embeddings wrapped in `pgvector.Vector`);
`list_documents(conn, workspace_id: int) -> list[dict]` (id, filename, page_count, created_at; ordered by filename)

**Produces (ingest):** `MAX_BYTES = 20 * 1024 * 1024`; `class FileTooBig(Exception)` ("File is too big (max 20 MB).");
`add_document(conn, ollama, uploads_dir: Path, workspace_id: int, filename: str, data: bytes) -> int`, in this order:
1. `name = PureWindowsPath(filename).name` (handles `\` and `/`)
2. `len(data) > MAX_BYTES` → `FileTooBig`
3. workspace missing → `NotFound`
4. `document_exists` → `AlreadyExists("{name} is already in this workspace.")` (before any embedding)
5. `read_document` → `chunk_pages` → `ollama.embed_documents`
6. Save to `uploads_dir / (uuid4().hex + suffix.lower())`; `stored_path` = that file name only
7. `with conn.transaction():` insert document (`page_count = len(pages)`) + chunks; on any error delete the saved file and re-raise

Tests (`conn`, `FakeOllama`, `tmp_path`):
- [ ] `test_add_txt_saves_rows_and_file`: listed as "notes.txt", chunk rows > 0, one file in uploads ending `.txt` and not named "notes.txt"
- [ ] `test_too_big_saves_nothing`: `MAX_BYTES + 1` bytes → `FileTooBig`, `embed_calls == 0`, uploads empty
- [ ] `test_duplicate_raises_before_embedding`: message "notes.txt is already in this workspace.", `embed_calls` unchanged
- [ ] `test_embedding_failure_leaves_nothing`: `fail_after = 1` → `OllamaUnavailable`, no document rows, uploads empty
- [ ] `test_database_failure_deletes_file`: monkeypatch `insert_chunks` to raise → no document row, uploads empty
- [ ] `test_unknown_workspace_raises_not_found`
- [ ] `test_folder_parts_are_stripped`: `"C:\\fakepath\\notes.txt"` → "notes.txt"; `"../../evil.txt"` → "evil.txt" (Review Focus 3)
- [ ] `test_unreadable_file_saves_nothing`: `"a.exe"` → `ReadError`, uploads empty
- [ ] Run (FAIL) → implement → run (PASS)
- [ ] Check with real Ollama + Postgres: `python context/try_add.py <path-to-a-pdf>` prints the chunk count
- [ ] Commit `feat: add documents with rollback`

### Task 7: Asking questions
**Files:** Create `app/rag.py`, `tests/test_rag.py`, `context/try_ask.py`; modify `app/ollama_client.py`, `app/db.py`, `tests/test_ollama_client.py`

**Produces (ollama):** `NUM_CTX = 8192`, `TEMPERATURE = 0.1`; `chat(system: str, user: str) -> str`: POST `/api/chat` with `messages` [system, user], `"stream": false`, `"options": {"num_ctx": 8192, "temperature": 0.1}`; returns `["message"]["content"]`; same error mapping

**Produces (db):** `count_chunks(conn, workspace_id: int) -> int`;
`search_chunks(conn, workspace_id: int, embedding: list[float], limit: int) -> list[dict]` (filename, page, text, distance): the SQL from spec section 6

**Produces (rag):** `TOP_K = 5`; `MAX_DISTANCE = 0.8` (loose start value; Task 11 measures the real one);
`SYSTEM_PROMPT` (exact text from spec section 6); `NOT_FOUND_MESSAGE = "I couldn't find this in your documents."`; `EMPTY_MESSAGE = "This workspace has no documents yet."`;
`@dataclass Answer(text: str, sources: list[dict], related: bool)` (each source: filename, page, text);
`build_prompt(question: str, chunks: list[dict]) -> str`; `parse_answer(reply: str, chunks: list[dict]) -> Answer`;
`ask(conn, ollama, workspace_id: int, question: str, max_distance: float = MAX_DISTANCE) -> Answer`
- `ask`: workspace missing → `NotFound`; no chunks → `EMPTY_MESSAGE` with no AI calls; `embed_query` → `search_chunks(TOP_K)`; best distance > `max_distance` → `NOT_FOUND_MESSAGE` with no chat; otherwise `chat` → `parse_answer`
- `parse_answer`: `reply.strip().rstrip(".") == "NOT_FOUND"` → not found; citations `\[(\d+)\]` within 1..len(chunks), unique, in order → sources; none valid → all chunks, `related=True`

Tests:
- [ ] `test_build_prompt_format`: exactly `"Excerpts:\n[1] (a.pdf, page 4)\nA text\n\n[2] (b.docx)\nB text\n\nQuestion: Q"`
- [ ] `test_parse_not_found`: `"NOT_FOUND"` and `"NOT_FOUND."`
- [ ] `test_parse_keeps_valid_ignores_invalid`: `"A [2] B [7] C [2]"` with 2 chunks → sources `[chunk 2]`, `related False`
- [ ] `test_parse_no_citations_is_related`
- [ ] `test_ask_empty_workspace_skips_ai`: `embed_calls == 0`, `chat_calls == 0`
- [ ] `test_ask_far_chunks_is_not_found`: `max_distance=-1` → `NOT_FOUND_MESSAGE`, `chat_calls == 0`
- [ ] `test_ask_returns_cited_source`: add "apples.txt" ("Apples are red."), `reply = "They are red [1]."` → first source "apples.txt"
- [ ] `test_ask_only_searches_its_workspace`: apples in "College", bananas in "Home"; ask in Home → no "apples.txt" source and "Apples" not in `last_user_prompt`
- [ ] `test_chat_sends_num_ctx_and_temperature` (MockTransport): options `{"num_ctx": 8192, "temperature": 0.1}`, `stream` false
- [ ] Run (FAIL) → implement → run (PASS)
- [ ] Check: `python context/try_ask.py "<question>"` answers with sources; while it runs, `ollama ps` shows CONTEXT 8192 and 100% GPU (if not: `NUM_CTX = 4096`)
- [ ] Commit `feat: answer questions with sources`

### Task 8: Deleting (database side)
**Files:** Modify `app/db.py`, `tests/test_db.py`

**Produces:** `delete_document(conn, document_id: int) -> str | None` (returns `stored_path`; `None` if missing);
`delete_workspace(conn, workspace_id: int) -> list[str] | None` (returns its documents' `stored_path`s; `None` if missing; one transaction)
- [ ] Tests: `test_delete_document_cascades_and_returns_path`; `test_delete_workspace_returns_paths_and_cascades`; `test_delete_missing_returns_none` (both functions)
- [ ] Run (FAIL) → implement → run (PASS) → commit `feat: delete documents and workspaces`

### Task 9: API routes and errors
**Files:** Create `app/main.py`, `tests/test_api.py`

**Produces:** dependencies `get_conn()` (a connection per request, closed afterwards), `get_ollama() -> OllamaClient`, `get_uploads_dir() -> Path`; startup runs `connect` + `init_db`, and if Postgres is down it logs and exits with "Database isn't running. Run: docker compose up -d"

| Route | Body | Success |
|---|---|---|
| `POST /api/workspaces` | `{"name"}` | 201 `{"id", "name"}` |
| `GET /api/workspaces` | | 200 list |
| `DELETE /api/workspaces/{id}` | | 204 |
| `GET /api/workspaces/{id}/documents` | | 200 list |
| `POST /api/workspaces/{id}/documents` | file (multipart) | 201 `{"id", "filename"}` |
| `DELETE /api/documents/{id}` | | 204 |
| `POST /api/workspaces/{id}/ask` | `{"question"}` | 200 `{"answer", "sources", "related"}` |

- Errors return `{"detail": message}`: `ReadError` 400, `FileTooBig` 413, `AlreadyExists` 409, `NotFound` 404, `OllamaUnavailable`/`ModelMissing` 503, `OllamaTimeout` 504, `psycopg.OperationalError` 503 with the database message, anything else 500 "Something went wrong." (details logged)
- Name: stripped, 1-100 characters, else 400 "Please enter a name (max 100 characters)." Question: stripped, 1-2000, else 400 "Please type a question (max 2000 characters)."
- Upload reads at most `MAX_BYTES + 1` bytes (`await file.read(MAX_BYTES + 1)`)
- Delete routes unlink `uploads_dir / path` for every returned path (`missing_ok=True`; any `OSError` is logged, not raised)
- Run: `uvicorn app.main:app --host 127.0.0.1 --port 8000`

Tests (`TestClient`, dependency overrides with `conn`, `FakeOllama`, `tmp_path`):
- [ ] Workspaces: create 201; duplicate 409 with the exact message; "college" after "College" 409; blank 400; 101 characters 400
- [ ] Upload: `.txt` 201 and listed; `.exe` 400 message; `MAX_BYTES + 1` 413; duplicate 409; unknown workspace 404
- [ ] Ask: answer + sources; blank question 400; 2001 characters 400; `fake.down = True` → 503 "Ollama isn't running. Start it and try again."
- [ ] Delete: document 204 and file gone; file already missing still 204; workspace 204 and files gone; unknown id 404
- [ ] Run (FAIL) → implement → run (PASS)
- [ ] Check: run uvicorn, open `http://127.0.0.1:8000/docs`, try each route
- [ ] Commit `feat: api routes with friendly errors`

### Task 10: Web page
**Files:** Create `app/static/index.html`, `app/static/style.css`, `app/static/app.js`; modify `app/main.py` (serve `/static`, `GET /` returns `index.html`), `tests/test_api.py`

**The page:** workspace dropdown + "New workspace" + "Delete workspace" (with `confirm()`); upload (`accept=".pdf,.docx,.txt,.md"`); document list with delete (with `confirm()`); question box + Ask; answer with source cards ("file, page N", or file only when page is null) or "Related passages"; "Processing..." and disabled buttons during requests; errors show the API's `detail`

- Text from documents and answers goes on the page **only** through `textContent`, never `innerHTML` (Review Focus 4)
- [ ] Test `test_index_is_served`: `GET /` → 200, `text/html`
- [ ] Manual check: full flow in the browser; upload a `.txt` containing `<b>x</b><script>alert(1)</script>`, ask about it → shown as plain text, no popup
- [ ] Commit `feat: web page`

### Task 11: Quality check and tuning
**Files:** Create `eval/questions.json`, `eval/docs/` (non-private sample documents, safe to publish), `eval/run_quality_check.py`; modify `app/chunker.py`, `app/ingest.py`, `app/ollama_client.py`

- `questions.json`: about 20 items `{"question", "expected_file", "expected_page" (or null), "answerable"}`, about 15 answerable and 5 not
- `chunk_pages` gets `size` and `overlap` parameters; `add_document` gets `chunk_size: int = CHUNK_SIZE`
- `chat` sends `"think": false` when the chat model name starts with `qwen3`
- The script rebuilds a "Quality check" workspace from `eval/docs/`; for each question: hit = expected file (and page if given) in the top 5; unanswerable → `ask` returns `NOT_FOUND_MESSAGE`. It prints hit rate, "not found" accuracy, and the average best distance for answerable vs unanswerable questions. Options `--chunk-size`, `--model`
- [ ] Run the baseline; try 500 and 1500; keep the best chunk size
- [ ] Set `MAX_DISTANCE` between the two average distances; re-run
- [ ] `ollama pull qwen3:8b`; run with `--model qwen3:8b`; keep the better model
- [ ] Commit `feat: quality check script and tuned settings`

### Task 12: Ship
**Files:** Create `Dockerfile`, `.dockerignore`; modify `docker-compose.yml`, `README.md`

- Image `python:3.14-slim`, installs `requirements.txt`; command `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Inside a container it must be `0.0.0.0`; the 127.0.0.1 rule is kept by publishing `"127.0.0.1:8000:8000"`
- Compose `app` service: `POSTGRES_HOST=db`, `POSTGRES_PORT=5432` (the inside port, not 5433), `OLLAMA_URL=http://host.docker.internal:11434`, `UPLOADS_DIR=/data/uploads` on a named volume, `depends_on: db: condition: service_healthy`
- Known risk: Ollama on Windows listens on 127.0.0.1 only, so the container may not reach it. Test this first. Exposing Ollama to the network is rejected, so if it fails we choose another way then
- README: run guide (replaces "How it will work"), Mermaid architecture diagram, quality-check results, demo video link
- [ ] Check: `docker compose up -d --build`, open `http://127.0.0.1:8000`, full flow works
- [ ] Commit `feat: run with docker compose` and `docs: readme`