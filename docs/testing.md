# Testing

Everything below was tested by hand on the real app running in Docker, with Ollama on the GPU.
Every bug found got an automatic test first, then a fix. The test suite runs on every push.

## Security (Task 13)

| Attack | What the app does | Commit |
|---|---|---|
| DNS rebinding: a website pretends to be `127.0.0.1` to read your documents | Requests not addressed to `127.0.0.1` or `localhost` get 400 | `75c53e2` |
| Cross-site request (CSRF): a website you visit secretly uploads or deletes | Writes from any other website (Origin) get 403 | `c304a0c` |
| Attack code in a filename: `<img src=x onerror=alert(1)>.txt` | Shown as plain text, no popup | (Task 10) |

## Strange files (Step 14a)

Uploaded by `context/try_strange_files.py` (made in memory, not committed). Final run: **10 of 10 as wanted**.

| File | Result |
|---|---|
| Password-locked PDF | Refused: "Couldn't read this file. It may be damaged or locked." |
| PDF with no text (like a scan) | Refused: "No text found. Scanned PDFs aren't supported yet." |
| Program renamed to `.pdf` | Refused: "Couldn't read this file…" |
| Program renamed to `.txt` | Refused: "Couldn't read this file…" (**was a 500, fixed**) |
| Empty Word file | Refused: "No text found." (**said "Scanned PDFs", fixed**) |
| Word file with text only in a table | Saved, and "What colour are plums?" → "Purple [1]" from `table.docx` (**text in tables was ignored, fixed**) |
| One byte over 20 MB | Refused: "File is too big (max 20 MB)." |
| Hindi and emoji in name and text | Saved; the name shows correctly on the page |
| Attack code in the filename | Saved; shown as plain text, no popup |
| Very long filename (300 characters) | Saved; but it squeezes the Delete button (**page layout, for Task 15**) |

### Bugs found and fixed

| Bug | Cause | Fix | Commit |
|---|---|---|---|
| A program renamed to `.txt` gave "Something went wrong." | The database refuses zero bytes (`\x00`) | `.txt`/`.md` with zero bytes are refused early; zero bytes are removed from PDF text | `1c40a3a` |
| Text inside Word tables was ignored | Only paragraphs were read | Tables are read too, in reading order, one row per line (`Plums \| purple`) | `5549b0c` |
| Empty Word or text files were told "Scanned PDFs aren't supported yet." | One message for all file types | The scanned hint only shows for PDFs | `feaa1b4` |

### Known limits

- **Scanned PDFs** (pictures of text) can't be read. That would need OCR (reading text from images).
- **Other languages:** an English question about a Hindi document wasn't found ("What colour are bananas?" against "केले पीले होते हैं"). The embedding model `nomic-embed-text` is mainly trained on English.
- **UTF-16 text files** (an old Notepad option) are refused, because they contain zero bytes.
- **Word tables:** cells with the same text in one row are kept once ("Yes | Yes" → "Yes").
- **Old uploads** keep their old chunks until deleted and uploaded again.

## Stopped services (Step 14b)

Each service was stopped while the app was running, then a question was asked on the page.

| What was stopped | Result |
|---|---|
| Ollama (quit from the taskbar) | The server answers at once with "Ollama isn't running. Start it and try again." Works again as soon as Ollama is back. (**page bug, fixed**) |
| The database (`docker compose stop db`) | Friendly error message, no crash. Works again after `docker compose start db`. |
| Everything (`docker compose down`, then `docker compose up -d`) | Workspaces, documents and answers are all still there. |

### Bugs found and fixed

| Bug | Cause | Fix | Commit |
|---|---|---|---|
| With Ollama stopped, the page seemed to do nothing, and the old answer stayed on screen | The red error box was at the very bottom of the page, out of view, and the previous answer was never cleared | The old answer is hidden as soon as a new question is sent; the error box sticks to the bottom of the window so it's always visible | `12b7058` |