# Task 15: New page design — build plan

**How to use:** one task at a time. Claude gives the full code for each task in chat; you create the files, run the checks and commit.

**Goal:** the page from the spec: sidebar layout, 9 new features, past questions saved in the database, and a status light.

**How it's built:** Python parts first, with tests written before the code (Tasks 1-4). Then the page, which only uses routes that already exist and are tested (Tasks 5-9). Docs last (Task 10).

**Spec:** `docs/superpowers/specs/2026-11-16-ui-redesign-design.md`

## Rules for every task

- Plain HTML, CSS and JavaScript; nothing from the internet.
- Outside text (filenames, answers, sources, questions, server messages) only with `textContent`.
- Run tests with `.venv\Scripts\python -m pytest -v`. Docker database must be running.
- After changes in `app/`: `docker compose up -d --build`, then Ctrl + F5.
- Commit after every task; push only when all tests pass.

## Things most likely to go wrong (each has a test or check below)

1. A filename with quotes or Hindi letters (`केले "v2".txt`) when deleting a document: its past answers must still be found and deleted → Task 1.
2. The same filename in two workspaces: deleting it in one must not touch the other's history → Task 1.
3. Ollama lists `nomic-embed-text:latest` while our setting says `nomic-embed-text`: must count as present → Task 3.
4. Ollama frozen (not answering): the status check must give up after 5 seconds, not 2 minutes → Task 3.
5. An answer with `[7]` when there are only 2 sources, or attack code in the answer: must stay plain text → Task 7.

---

### Task 1: Past questions — database

**Files:** modify `tests/conftest.py`, `tests/test_db.py`, `app/db.py`

**Makes (used by Task 2):**
- `insert_question(conn, workspace_id: int, question: str, answer: str, sources: list[dict], related: bool) -> int`
- `list_questions(conn, workspace_id: int) -> list[dict]`: keys `id, question, answer, sources, related, created_at`, newest first (`ORDER BY id DESC`), at most 50
- `clear_questions(conn, workspace_id: int) -> None`
- `delete_document(conn, document_id) -> str | None`: same as before, and also deletes that workspace's questions whose sources quote its filename

- [ ] **Step 1: tests.** In `conftest.py` the drop line becomes `DROP TABLE IF EXISTS questions, chunks, documents, workspaces`. In `test_db.py`:

```python
SOURCE = {"number": 1, "filename": "notes.txt", "page": None, "text": "Apples are red."}

def all_question_rows(conn) -> int:
    return conn.execute("SELECT count(*) AS n FROM questions").fetchone()["n"]

def test_insert_and_list_questions_newest_first(conn):
    ws = create_workspace(conn, "College")
    insert_question(conn, ws, "First?", "Red [1].", [SOURCE], False)
    insert_question(conn, ws, "Second?", "Some passages.", [], True)
    rows = list_questions(conn, ws)
    assert [r["question"] for r in rows] == ["Second?", "First?"]
    assert rows[1]["sources"] == [SOURCE]
    assert rows[0]["related"] is True

def test_list_questions_keeps_latest_50(conn):
    ws = create_workspace(conn, "College")
    for i in range(51):
        insert_question(conn, ws, f"Q{i}", "A", [], False)
    rows = list_questions(conn, ws)
    assert len(rows) == 50
    assert rows[0]["question"] == "Q50"

def test_clear_questions_only_clears_that_workspace(conn):
    a, b = create_workspace(conn, "A"), create_workspace(conn, "B")
    insert_question(conn, a, "A?", "x", [], False)
    insert_question(conn, b, "B?", "x", [], False)
    clear_questions(conn, a)
    assert list_questions(conn, a) == []
    assert len(list_questions(conn, b)) == 1

def test_delete_workspace_deletes_its_questions(conn):
    ws = create_workspace(conn, "College")
    insert_question(conn, ws, "Q?", "A", [], False)
    delete_workspace(conn, ws)
    assert all_question_rows(conn) == 0

def test_delete_document_deletes_questions_that_quote_it(conn):
    ws = create_workspace(conn, "College")
    name = 'केले "v2".txt'
    doc = add_document_row(conn, ws, name, "a.txt")
    insert_question(conn, ws, "Quotes it?", "x [1]", [{**SOURCE, "filename": name}], False)
    insert_question(conn, ws, "Other?", "x [1]", [{**SOURCE, "filename": "other.txt"}], False)
    insert_question(conn, ws, "No sources?", "Not found.", [], False)
    delete_document(conn, doc)
    assert [r["question"] for r in list_questions(conn, ws)] == ["No sources?", "Other?"]

def test_delete_document_keeps_other_workspaces_history(conn):
    a, b = create_workspace(conn, "A"), create_workspace(conn, "B")
    doc = add_document_row(conn, a, "notes.txt", "a.txt")
    insert_question(conn, b, "B?", "x [1]", [SOURCE], False)
    delete_document(conn, doc)
    assert len(list_questions(conn, b)) == 1
```

- [ ] **Step 2:** run the tests → **expected: collection error** (`cannot import name 'clear_questions'`). Commit `test: past questions in the database` (no push yet).
- [ ] **Step 3: code.** In `app/db.py`: add the `questions` table from the spec to `SCHEMA`; the three functions; `sources` goes in with `psycopg.types.json.Jsonb(sources)`. `delete_document` runs inside `with conn.transaction():` — `DELETE FROM documents ... RETURNING workspace_id, filename, stored_path`, then `DELETE FROM questions WHERE workspace_id = %s AND sources @> %s` with `Jsonb([{"filename": filename}])`.
- [ ] **Step 4:** run the tests → **expected: 96 passed**. Commit `feat: past questions in the database`, push.

### Task 2: Past questions — routes

**Files:** modify `tests/test_api.py`, `app/main.py`
**Uses:** Task 1's functions. **Makes:** `GET` and `DELETE /api/workspaces/{id}/questions`; asking saves.

- [ ] **Step 1: tests** in `test_api.py`:

```python
def test_ask_saves_the_question(client, fake):
    ws = make_workspace(client)
    upload(client, ws, "apples.txt", b"Apples are red.")
    fake.reply = "They are red [1]."
    client.post(f"/api/workspaces/{ws}/ask", json={"question": "Are apples red?"})
    history = client.get(f"/api/workspaces/{ws}/questions").json()
    assert [h["question"] for h in history] == ["Are apples red?"]
    assert history[0]["answer"] == "They are red [1]."
    assert history[0]["sources"][0]["filename"] == "apples.txt"

def test_failed_ask_saves_nothing(client, fake):
    ws = make_workspace(client)
    upload(client, ws)
    fake.down = True
    client.post(f"/api/workspaces/{ws}/ask", json={"question": "Are apples red?"})
    assert client.get(f"/api/workspaces/{ws}/questions").json() == []

def test_clear_questions(client, fake):
    ws = make_workspace(client)
    upload(client, ws)
    client.post(f"/api/workspaces/{ws}/ask", json={"question": "Are apples red?"})
    assert client.delete(f"/api/workspaces/{ws}/questions").status_code == 204
    assert client.get(f"/api/workspaces/{ws}/questions").json() == []

@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_questions_of_unknown_workspace_is_404(client, method):
    response = client.request(method, "/api/workspaces/999/questions")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found."}
```

- [ ] **Step 2:** run → **expected: 5 failed** (404 for the missing routes, and nothing saved). Commit `test: routes for past questions` (no push yet).
- [ ] **Step 3: code.** `ask_question` calls `db.insert_question(...)` after `ask(...)` returns, before replying. New routes `list_questions` and `clear_questions` check `db.get_workspace` first (`raise db.NotFound()`), like `list_documents`.
- [ ] **Step 4:** → **expected: 101 passed**. Commit `feat: routes for past questions`, push.

### Task 3: Status check — Ollama models

**Files:** modify `tests/test_ollama_client.py`, `tests/fakes.py`, `app/ollama_client.py`
**Makes:** `OllamaClient.missing_models() -> list[str]`, raises `OllamaUnavailable` / `OllamaTimeout`. `FakeOllama` gets `self.missing = []` and the same method (raises `OllamaUnavailable` when `down`).

- [ ] **Step 1: tests:**

```python
def tags(names):
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": n} for n in names]})
    return handler

def test_missing_models_none_missing():
    # "nomic-embed-text" in our settings means "nomic-embed-text:latest"
    assert make_client(tags(["nomic-embed-text:latest", "llama3.1:8b"])).missing_models() == []

def test_missing_models_lists_the_missing_one():
    assert make_client(tags(["nomic-embed-text:latest"])).missing_models() == ["llama3.1:8b"]

def test_missing_models_when_ollama_is_off():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)
    with pytest.raises(OllamaUnavailable):
        make_client(handler).missing_models()

def test_missing_models_when_ollama_hangs():
    def handler(request):
        raise httpx.ReadTimeout("too slow", request=request)
    with pytest.raises(OllamaTimeout):
        make_client(handler).missing_models()
```

- [ ] **Step 2:** → **expected: 4 failed** (`no attribute 'missing_models'`). Commit `test: check which models are missing` (no push yet).
- [ ] **Step 3: code.** `self.http.get("/api/tags", timeout=5.0)`, same `ConnectError` / `TimeoutException` handling as `_post`. A name without `:` gets `:latest` before comparing. Returns our models in the order embed, chat.
- [ ] **Step 4:** → **expected: 105 passed**. Commit `feat: check which models are missing`, push.

### Task 4: Status check — route

**Files:** modify `tests/test_api.py`, `app/main.py`
**Uses:** Task 3. **Makes:** `GET /api/health` → `{"database", "ollama", "missing_models", "message"}`, always 200; new dependency `get_conn_or_none()` (yields `None` when the database can't be reached).

- [ ] **Step 1: tests.** In the `client` fixture add `app.dependency_overrides[get_conn_or_none] = lambda: conn` (and import it).

```python
def test_health_ready(client):
    assert client.get("/api/health").json() == {
        "database": "ok", "ollama": "ok", "missing_models": [], "message": "Ready"}

def test_health_ollama_down(client, fake):
    fake.down = True
    body = client.get("/api/health").json()
    assert body["ollama"] == "down"
    assert body["message"] == "Ollama isn't running. Start it and try again."

def test_health_model_missing(client, fake):
    fake.missing = ["llama3.1:8b"]
    body = client.get("/api/health").json()
    assert body["missing_models"] == ["llama3.1:8b"]
    assert body["message"] == "Model llama3.1:8b not found. Run: ollama pull llama3.1:8b"

def test_health_database_down(client):
    app.dependency_overrides[get_conn_or_none] = lambda: None
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["database"] == "down"
    assert response.json()["message"] == "Database isn't running. Run: docker compose up -d"
```

- [ ] **Step 2:** → **expected: collection error** (`cannot import name 'get_conn_or_none'`). Commit `test: status check route` (no push yet).
- [ ] **Step 3: code.** `get_conn_or_none` catches `psycopg.OperationalError` on connect. The route runs `SELECT 1` (also in a `try`), calls `ollama.missing_models()` inside `try ... except OllamaError`. Message order: database down, then Ollama down, then first missing model (`str(ModelMissing(name))`), else `"Ready"`.
- [ ] **Step 4:** → **expected: 109 passed**. Commit `feat: status check route`, push.

### Task 5: New layout, light/dark switch, icon, long filenames (#10, #3)

**Files:** rewrite `app/static/index.html`, `app/static/style.css`; modify `app/static/app.js`; create `app/static/favicon.svg`
**Keeps every existing id** (`workspace-select`, `delete-workspace`, `new-workspace-form`, `new-workspace-name`, `upload-form`, `file-input`, `document-list`, `ask-form`, `question`, `answer`, `answer-text`, `sources-title`, `sources`, `status`, `error`), so the current JavaScript keeps working.
**New ids:** `theme-toggle`, `health` (empty until Task 9).

- Top bar, `<aside>` sidebar (280 px), `<main>`; under 760 px the sidebar goes on top.
- Colours: light in `:root`; dark in `[data-theme="dark"]` and in `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }`. New tokens `--success`, `--warning`.
- `app.js`: on start, read the saved theme from `localStorage` (inside `try`); the button sets `document.documentElement.dataset.theme` and saves it.
- Filenames: one line, `text-overflow: ellipsis`, `title` = full name.
- **Check (manual):** the page looks like the preview; workspace, upload, ask and delete still work; light/dark switch works and is remembered after Ctrl + F5; the 300-character filename shows "…" with the Delete button intact; no `/favicon.ico` 404 in `docker compose logs app --tail 20`; a window under 760 px puts the sidebar on top.
- Commit `feat: new page layout with light and dark switch`, push.

### Task 6: Welcome screens, small messages, "Are you sure?" box (#8, #4, #5)

**Files:** `index.html`, `style.css`, `app.js`
**Makes:**
- `notify(id, text)`: puts `text` in a `<p class="note" role="status">` (ids `workspace-note`, `upload-note`, `history-note`) and empties it after 4 s.
- `confirmBox(title, text) -> Promise<boolean>`: uses `<dialog id="confirm">` with `#confirm-title`, `#confirm-text`, Cancel focused first; Esc = false.
- `updateWelcome(documentCount)`: shows `#welcome` (texts from the spec) and hides `#ask-form` when there's no workspace or no document.
- All `confirm(...)` calls are replaced by `await confirmBox(...)`.
- **Check (manual):** new empty workspace → welcome with steps 1 and 2, no question box; upload → "Uploaded notes.txt" next to the button, gone after 4 s; delete → our box; Esc and Cancel keep the file; Enter right after it opens does not delete.
- Commit `feat: welcome screens, messages and confirm box`, push.

### Task 7: Clickable sources and past questions (#6, #7)

**Files:** `index.html`, `style.css`, `app.js`
**Uses:** Task 2's routes, Task 6's `confirmBox` and `notify`.
**Makes:**
- `addCitations(element, text, numbers: Set<number>)`: splits `text` on `/(\[\d+\])/`; a match whose number is in `numbers` becomes a `<button class="cite">`; everything else is a text node.
- Source cards get `id="source-{n}"`; clicking a citation scrolls to it and adds the `flash` class for 2 s.
- `loadHistory()`: `GET .../questions` into `#history-list` (question + time); clicking one calls `showAnswer({answer, sources, related})`. Runs after loading documents and after each ask. `#clear-history` → `confirmBox` → `DELETE` → `notify("history-note", "History cleared")`.
- **Check (manual):** click [1] → jumps and flashes; ask 2 questions → both listed, newest first; click the older one → its answer and sources come back; restart with `docker compose restart app` → history still there; delete a document → the past answers that quoted it are gone; a question whose answer contains `<b>hi</b>` or `[7]` shows it as plain text.
- Commit `feat: clickable sources and past questions`, push.

### Task 8: Drag and drop, several files (#2)

**Files:** `index.html`, `style.css`, `app.js`
**Makes:** `uploadFiles(files: FileList)`. For each file in order: `await busy(\`File ${i} of ${n}: ${file.name}...\`, work)`, where `work` catches its own error so the loop goes on. Results go in `#upload-results` as ✓ name / ✗ name — reason. `#upload-form` is the drop zone (`dragover` adds class `dragging`, `drop` calls `uploadFiles`); `<input type="file" multiple>`.
- **Check (manual):** drop 3 files where one is already uploaded → 2 ✓ and 1 ✗ "… is already in this workspace."; drop a `.exe` → ✗ "Only .pdf, .docx, .txt and .md files are supported."; the timer restarts for each file; "Choose files" with 2 files works the same.
- Commit `feat: drag and drop several files`, push.

### Task 9: Status light (#9)

**Files:** `index.html`, `style.css`, `app.js`
**Uses:** Task 4's route. **Makes:** `checkHealth()`: sets `#health` class `ok` / `warn` / `down` and its text to `message`; runs on start, every 30 s, and in `busy()`'s `catch`.
- **Check (manual):** green "Ready"; quit Ollama → red within 30 s (or at once after asking); start Ollama → green again; `docker compose stop db` → red "Database isn't running…"; `docker compose start db` → green.
- Commit `feat: status light`, push.

### Task 10: Docs

**Files:** `docs/testing.md` (new section "New page (Task 15)" with every manual check above and its result), `README.md` (Status box ticked, the new features, new routes, test count). Whole files given in chat.
- Commit `docs: testing and readme for the new page`, push.