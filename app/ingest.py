import uuid
from pathlib import Path, PureWindowsPath

import psycopg

from app import db
from app.chunker import chunk_pages
from app.reader import read_document

MAX_BYTES = 20 * 1024 * 1024  # 20 MB


class FileTooBig(Exception):
    def __init__(self):
        super().__init__("File is too big (max 20 MB).")


def add_document(
    conn: psycopg.Connection,
    ollama,
    uploads_dir: Path,
    workspace_id: int,
    filename: str,
    data: bytes,
) -> int:
    # 1. Keep only the file's own name: "C:\fakepath\notes.txt" -> "notes.txt",
    #    "../../evil.txt" -> "evil.txt". PureWindowsPath understands both \ and /.
    name = PureWindowsPath(filename).name

    # 2. Cheap checks first, so a bad upload never reaches the slow AI step.
    if len(data) > MAX_BYTES:
        raise FileTooBig()
    if db.get_workspace(conn, workspace_id) is None:
        raise db.NotFound()
    if db.document_exists(conn, workspace_id, name):
        raise db.AlreadyExists(f"{name} is already in this workspace.")

    # 3. The slow part, all in memory: read, cut into chunks, embed.
    pages = read_document(name, data)
    chunks = chunk_pages(pages)
    embeddings = ollama.embed_documents([chunk.text for chunk in chunks])

    # 4. Save the original file under a random name ...
    uploads_dir.mkdir(parents=True, exist_ok=True)
    stored_path = uuid.uuid4().hex + Path(name).suffix.lower()
    file_path = uploads_dir / stored_path
    file_path.write_bytes(data)

    # 5. ... then the database rows, all or nothing. If saving fails, delete the file again.
    try:
        with conn.transaction():
            document_id = db.insert_document(conn, workspace_id, name, stored_path, len(pages))
            db.insert_chunks(conn, document_id, chunks, embeddings)
    except Exception:
        file_path.unlink(missing_ok=True)
        raise

    return document_id