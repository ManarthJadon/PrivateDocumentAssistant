# Task 15: Professional page design — design

Date: 2026-11-16. Status: approved by the user before building.

## Goal

Make the page look and feel like a finished product: a recruiter should understand the app from one screenshot, and every action should clearly say what happened.

Rules that stay the same:
- Plain HTML, CSS and JavaScript. No frameworks.
- Nothing loaded from the internet (no web fonts, no icon libraries).
- Text from documents, answers and filenames goes on the page only with `textContent`, never `innerHTML`.
- Every check in `docs/testing.md` must still pass on the new page.

## Features

| # | Feature | Needs Python? |
|---|---|---|
| 2 | Drag and drop, several files at once | No |
| 3 | Long filenames cut with "…", full name on hover | No |
| 4 | Small messages next to the action ("Uploaded", "Deleted") | No |
| 5 | Our own "Are you sure?" box instead of the browser popup | No |
| 6 | Click [1] in the answer to jump to that source | No |
| 7 | Past questions and answers, saved per workspace | Yes: table + 2 routes |
| 8 | Welcome screen for a new or empty workspace | No |
| 9 | Status light for Ollama and the database | Yes: 1 route |
| 10 | Light/dark switch and a page icon (favicon) | No |

Already done before Task 15: waiting message with a live timer, Enter to ask.

## 1. Layout

- **Top bar:** app name, "Your documents never leave this computer", the status light (#9) and the theme button (#10).
- **Left sidebar (280 px):** workspace picker, "New workspace", "Delete workspace", the document list, and the upload area.
- **Main area:** the question box, the current answer with its sources, then "Past questions".
- **Narrow windows (under 760 px):** the sidebar moves above the main area.
- The waiting message and the red error box stay at the bottom of the window (`position: sticky`), as now.

## 2. Page-only features

**#2 Drag and drop, several files**
- The upload area accepts files dropped on it, or picked with "Choose files" (`<input type="file" multiple>`).
- Files are sent **one after another** through the existing route `POST /api/workspaces/{id}/documents`. No Python change.
- The waiting message shows `File 2 of 5: notes.pdf... 0:12`.
- Afterwards, a list shows each file with ✓ or ✗ and the server's reason ("notes.txt is already in this workspace."). One failed file doesn't stop the rest.
- Why one after another: uploads use the GPU for embeddings. Sending 5 at once would not be faster and makes the timer meaningless.

**#3 Long filenames**
- One line, cut with "…" (`text-overflow: ellipsis`). The full name shows on hover (`title`).
- The Delete button never gets squeezed (fixes the known problem from Step 14a).

**#4 Small messages**
- After create, upload, delete or clear: a short message under that button, for example "Deleted bananas.txt". It disappears after 4 seconds.
- `role="status"` so screen readers announce it.
- Errors keep using the existing red error box.

**#5 "Are you sure?" box**
- Uses the browser's built-in `<dialog>` element (`showModal()`). It blocks the rest of the page, closes with Esc, and needs no library.
- "Cancel" has the focus by default, so pressing Enter by accident never deletes.
- Used for: delete document, delete workspace, clear past questions. The text says what will be lost, for example: "Delete Fruit guide.pdf? Past answers that quote it are deleted too. This can't be undone."

**#6 Clickable sources**
- The answer text is split at `[1]`, `[2]`, ... Each number that matches a source becomes a small button. Everything else stays plain text (still no `innerHTML`).
- Clicking it scrolls to that source card and highlights it for 2 seconds.

**#8 Welcome screens**
- No workspaces yet: "Create your first workspace" with one short line about what a workspace is.
- Workspace with no documents: "1. Upload a PDF, Word, .txt or .md file. 2. Ask a question. Answers show their sources." The question box is hidden until there is a document.

**#10 Light/dark switch and icon**
- By default the page follows the Windows setting, as now.
- The button switches between light and dark. The choice is remembered in the browser (`localStorage`); if the browser blocks that, the page still works.
- New file `app/static/favicon.svg` (a small document with a lock), linked with `<link rel="icon">`. This also stops the `/favicon.ico` 404 in the logs.

## 3. Past questions (#7)

**Database:** a new table, added to `SCHEMA` in `app/db.py`:

```sql
CREATE TABLE IF NOT EXISTS questions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id bigint NOT NULL REFERENCES workspaces ON DELETE CASCADE,
    question text NOT NULL,
    answer text NOT NULL,
    sources jsonb NOT NULL,
    related boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

- `sources` keeps the sources exactly as they were shown (number, filename, page, text), so an old answer still makes sense later.
- **Deleting a workspace** deletes its questions automatically (`ON DELETE CASCADE`).
- **Deleting a document** also deletes the past answers that quote it, in the same transaction. Otherwise its text would live on in the history, which breaks our privacy promise ("deleting a document deletes it"). The rows are found with `sources @> '[{"filename": "..."}]'` ("does the sources list contain this filename?").

**New functions in `app/db.py`:** `insert_question`, `list_questions` (newest first, at most 50), `clear_questions`. `delete_document` is changed as described above.

**Routes in `app/main.py`:**

| Route | What it does |
|---|---|
| `POST /api/workspaces/{id}/ask` (changed) | After a successful answer, saves it. Answers that failed (Ollama off, timeout) are not saved. "Not found" answers are saved. |
| `GET /api/workspaces/{id}/questions` (new) | Past questions, newest first. 404 if the workspace doesn't exist. |
| `DELETE /api/workspaces/{id}/questions` (new) | Clears that workspace's history (204). |

**Page:** "Past questions" under the current answer, showing the question and its time. Clicking one shows its answer and sources in the answer card. A "Clear history" button with the "Are you sure?" box.

## 4. Status light (#9)

**Route:** `GET /api/health`. It always answers 200, so the page can show what's wrong:

```json
{"database": "ok", "ollama": "ok", "missing_models": [], "message": "Ready"}
```

- **Database:** opens a connection and runs `SELECT 1`. If that fails: `"database": "down"`.
- **Ollama:** new method `OllamaClient.missing_models()` asks Ollama for its model list (`GET /api/tags`) and returns which of our two models are missing. A name without a tag counts as `:latest` (`nomic-embed-text` = `nomic-embed-text:latest`). If Ollama can't be reached: `"ollama": "down"`.
- **message:** the same friendly text the app already uses, for example "Ollama isn't running. Start it and try again."

**Light:**

| Colour | Meaning |
|---|---|
| Green "Ready" | Database and Ollama OK, both models there |
| Amber | A model is missing (shows "Run: ollama pull ...") |
| Red | Ollama or the database is down |

The page checks when it opens, every 30 seconds, and straight after any error. The light uses colour **and** text, so it also works for colour-blind users.

## 5. Files that change

| File | Change |
|---|---|
| `app/static/index.html` | New layout, `<dialog>`, upload area, past questions, status light, theme button, favicon link |
| `app/static/style.css` | Rewritten for the new layout; same colour token idea, plus `data-theme` |
| `app/static/app.js` | All page features above |
| `app/static/favicon.svg` | New |
| `app/db.py` | `questions` table, 3 new functions, `delete_document` change |
| `app/main.py` | Save after asking, 2 history routes, health route |
| `app/ollama_client.py` | `missing_models()` |
| `tests/test_db.py`, `tests/test_api.py`, `tests/test_ollama_client.py` | New tests (written first) |
| `README.md`, `docs/testing.md` | Updated at the end |

No changes to reading, chunking, embeddings, search or the AI prompt.

## 6. Testing

**Automatic tests (written first, they fail, then the code makes them pass):**
- Database: save and list questions (newest first, max 50); clear; deleting a workspace deletes its questions; deleting a document deletes only the questions that quote it.
- API: asking saves the question; a failed ask saves nothing; list and clear routes; 404 for an unknown workspace; health says OK, Ollama down, model missing, and database down.
- Ollama client: `missing_models()` with both models present, one missing, the `:latest` rule, and Ollama off.

**Manual checks on the page** (written down in `docs/testing.md`):
- Each of the 9 features works in light and dark.
- 3 files dropped at once, one of them a duplicate: 2 ✓ and 1 ✗ with its reason.
- Attack code in a filename and in an answer still shows as plain text.
- Ollama quit: the light turns red within 30 seconds.
- Narrow window: the sidebar moves above the main area.
- Keyboard only: Tab reaches every button, Esc closes the "Are you sure?" box.

## 7. Not included (later, if ever)

- A real progress bar for one big upload (needs background jobs).
- Searching inside past questions.
- Uploading several files at the same time (in parallel).