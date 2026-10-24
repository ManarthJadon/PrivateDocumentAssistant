# Private Document Assistant

![tests](https://github.com/ManarthJadon/PrivateDocumentAssistant/actions/workflows/tests.yml/badge.svg)

Ask questions about your own documents and get answers with sources. Everything runs on your own computer: no cloud, no API keys, and your documents never leave your machine.

## Status

Work in progress (7 of 12 build steps done).

- [x] Settings from `.env`
- [x] Reading PDF, Word (.docx), .txt and .md files
- [x] Cutting text into chunks (~1000 characters, never across PDF pages)
- [x] Database tables and workspaces (PostgreSQL + pgvector)
- [x] Embeddings with a local model (Ollama, `nomic-embed-text`)
- [x] Adding a document, all-or-nothing (nothing half-saved if something fails)
- [x] Answering questions with numbered sources (`llama3.1:8b`)
- [ ] Deleting documents and workspaces
- [ ] Web API (FastAPI)
- [ ] Web page
- [ ] Quality check (~20 test questions)
- [ ] One-command Docker run, demo video

## How it works

1. You create a **workspace** (for example "College") and upload documents into it.
2. The app reads the text and cuts it into small overlapping chunks.
3. A local model turns each chunk into an **embedding** (768 numbers that capture its meaning), stored in PostgreSQL with pgvector.
4. You ask a question. The app finds the 5 chunks closest in meaning, in that workspace only.
5. A local model answers using only those chunks and cites them like [1] and [2], so you can see the file (and page, for PDFs) behind each fact.

### When the answer isn't in your documents

The app says "I couldn't find this in your documents." instead of guessing. Two checks make sure of that:

- **Before the AI:** if even the closest chunk is far away in meaning, the model is never asked.
- **The AI itself:** it's told to reply `NOT_FOUND` when the excerpts don't contain the answer.

## Stack

- Python 3.14 + FastAPI
- PostgreSQL 17 + pgvector, in Docker
- Ollama on your own GPU: `nomic-embed-text` (embeddings), `llama3.1:8b` (answers; context 8192, temperature 0.1)
- psycopg with plain SQL (no ORM), no LangChain
- Plain HTML, CSS and JavaScript
- pytest + GitHub Actions (tests run on every push, with a fake Ollama)

## Privacy

- The app only listens on `127.0.0.1` (your own computer), so other devices can't reach it.
- The database port is also only open to your own computer.
- Uploaded files and the database stay on your disk and are never committed to git.
- Text inside your documents is treated as data, never as instructions to the AI.

## Run the tests

You need Python 3.14, [uv](https://docs.astral.sh/uv/) and Docker Desktop.

1. Copy `.env.example` to `.env` and choose your own database password in it.
2. Start the database: `docker compose up -d`
3. Create the test database (once): `docker compose exec db createdb -U docassistant docassistant_test`
4. Install: `uv venv`, then `uv pip install -r pyproject.toml --group dev`
5. Run: `.venv\Scripts\python -m pytest -v` (on Mac/Linux: `.venv/bin/python -m pytest -v`)

The tests don't need Ollama. They use a fake one.

## Project layout

| Path | What it does |
|---|---|
| `app/config.py` | Reads settings from `.env` |
| `app/reader.py` | Gets the text out of PDF, Word, .txt and .md files |
| `app/chunker.py` | Cuts text into chunks |
| `app/ollama_client.py` | Talks to Ollama (embeddings and answers) |
| `app/db.py` | All SQL: tables, workspaces, documents, chunks, search |
| `app/ingest.py` | Adds a document: check, read, chunk, embed, save |
| `app/rag.py` | Answers a question: search, prompt, read the reply, sources |
| `tests/` | Unit and database tests, plus the fake Ollama |
| `docs/` | Design spec and build plan |