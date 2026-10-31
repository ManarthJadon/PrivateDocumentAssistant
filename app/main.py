import logging
from contextlib import asynccontextmanager
from functools import cache
from pathlib import Path, PureWindowsPath

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import db
from app.config import get_settings
from app.ingest import MAX_BYTES, FileTooBig, add_document
from app.ollama_client import ModelMissing, OllamaClient, OllamaTimeout, OllamaUnavailable
from app.rag import ask
from app.reader import ReadError

log = logging.getLogger("app")

DB_DOWN = "Database isn't running. Run: docker compose up -d"
STATIC_DIR = Path(__file__).parent / "static"


# --- starting up ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts: check the database and create the tables.
    try:
        conn = db.connect(get_settings().db_conninfo)
    except psycopg.OperationalError:
        log.error(DB_DOWN)
        raise SystemExit(1)
    db.init_db(conn)
    conn.close()
    yield  # the server runs here


app = FastAPI(title="Private Document Assistant", lifespan=lifespan)
# Only answer requests addressed to this computer. This stops DNS rebinding: a website
# pretending to be 127.0.0.1 so that your browser lets it read your documents.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
ALLOWED_ORIGINS = {"http://127.0.0.1:8000", "http://localhost:8000"}


@app.middleware("http")
async def block_other_websites(request: Request, call_next):
    # Browsers say which website a request came from. This stops a website you visit
    # from secretly uploading or deleting things here. Tools like curl send no Origin.
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD") and origin is not None and origin not in ALLOWED_ORIGINS:
        return JSONResponse({"detail": "This request came from another website."}, status_code=403)
    return await call_next(request)


# --- dependencies: what each route gets handed (tests swap these) ---

def get_conn():
    conn = db.connect(get_settings().db_conninfo)
    try:
        yield conn
    finally:
        conn.close()


@cache
def get_ollama() -> OllamaClient:
    settings = get_settings()
    return OllamaClient(settings.ollama_url, settings.embed_model, settings.chat_model)


def get_uploads_dir() -> Path:
    return get_settings().uploads_dir


# --- turning errors into friendly replies ---

FRIENDLY_ERRORS = {
    ReadError: 400,
    FileTooBig: 413,
    db.AlreadyExists: 409,
    db.NotFound: 404,
    OllamaUnavailable: 503,
    ModelMissing: 503,
    OllamaTimeout: 504,
}


async def friendly_error(request: Request, error: Exception) -> JSONResponse:
    status = next(code for kind, code in FRIENDLY_ERRORS.items() if isinstance(error, kind))
    return JSONResponse({"detail": str(error)}, status_code=status)


for kind in FRIENDLY_ERRORS:
    app.add_exception_handler(kind, friendly_error)


@app.exception_handler(psycopg.OperationalError)
async def database_down(request: Request, error: Exception) -> JSONResponse:
    log.error("Database error", exc_info=error)
    return JSONResponse({"detail": DB_DOWN}, status_code=503)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
    log.error("Unexpected error", exc_info=error)  # full details for you, in the terminal
    return JSONResponse({"detail": "Something went wrong."}, status_code=500)


# --- checking what the user typed ---

class WorkspaceIn(BaseModel):
    name: str


class QuestionIn(BaseModel):
    question: str


def clean(text: str, max_length: int, message: str) -> str:
    text = text.strip()
    if not 1 <= len(text) <= max_length:
        raise HTTPException(status_code=400, detail=message)
    return text


def remove_files(uploads_dir: Path, names: list[str]) -> None:
    # A file that's already gone, or can't be deleted, must not stop the delete.
    for name in names:
        try:
            (uploads_dir / name).unlink(missing_ok=True)
        except OSError:
            log.exception("Couldn't delete uploads/%s", name)


# --- workspaces ---

@app.post("/api/workspaces", status_code=201)
def create_workspace(body: WorkspaceIn, conn=Depends(get_conn)):
    name = clean(body.name, 100, "Please enter a name (max 100 characters).")
    return {"id": db.create_workspace(conn, name), "name": name}


@app.get("/api/workspaces")
def list_workspaces(conn=Depends(get_conn)):
    return db.list_workspaces(conn)


@app.delete("/api/workspaces/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: int, conn=Depends(get_conn), uploads_dir=Depends(get_uploads_dir)):
    names = db.delete_workspace(conn, workspace_id)
    if names is None:
        raise db.NotFound()
    remove_files(uploads_dir, names)


# --- documents ---

@app.get("/api/workspaces/{workspace_id}/documents")
def list_documents(workspace_id: int, conn=Depends(get_conn)):
    if db.get_workspace(conn, workspace_id) is None:
        raise db.NotFound()
    return db.list_documents(conn, workspace_id)


@app.post("/api/workspaces/{workspace_id}/documents", status_code=201)
def upload_document(
    workspace_id: int,
    file: UploadFile,
    conn=Depends(get_conn),
    ollama=Depends(get_ollama),
    uploads_dir=Depends(get_uploads_dir),
):
    filename = file.filename or ""
    data = file.file.read(MAX_BYTES + 1)  # one byte more than allowed is enough to say "too big"
    document_id = add_document(conn, ollama, uploads_dir, workspace_id, filename, data)
    return {"id": document_id, "filename": PureWindowsPath(filename).name}


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: int, conn=Depends(get_conn), uploads_dir=Depends(get_uploads_dir)):
    name = db.delete_document(conn, document_id)
    if name is None:
        raise db.NotFound()
    remove_files(uploads_dir, [name])


# --- asking ---

@app.post("/api/workspaces/{workspace_id}/ask")
def ask_question(workspace_id: int, body: QuestionIn, conn=Depends(get_conn), ollama=Depends(get_ollama)):
    question = clean(body.question, 2000, "Please type a question (max 2000 characters).")
    answer = ask(conn, ollama, workspace_id, question)
    return {"answer": answer.text, "sources": answer.sources, "related": answer.related}


# --- the web page ---

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")