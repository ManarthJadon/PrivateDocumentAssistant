# Private Document Assistant

Ask questions about your own documents and get answers with sources. Everything runs on your own computer, so your documents never leave it.

## Status

Work in progress. Just started.

## Planned stack

- Python + FastAPI (backend)
- Plain HTML, CSS and JavaScript (web page)
- Ollama (local AI model)
- PostgreSQL + pgvector (stores document chunks and finds the closest ones)
- Docker Compose (run the whole app with one command)

## How it will work

1. Upload a PDF, Word file or notes.
2. The app cuts the text into small chunks and saves them in the database.
3. You ask a question. The app finds the best-matching chunks.
4. The local model answers using only those chunks and shows which file and page they came from.