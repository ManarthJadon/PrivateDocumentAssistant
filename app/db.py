import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app.chunker import Chunk


class NotFound(Exception):
    def __init__(self):
        super().__init__("Not found.")


class AlreadyExists(Exception):
    """Its text is the message shown to the user."""


# --- connecting and creating the tables ---

def connect(conninfo: str) -> psycopg.Connection:
    # autocommit: every statement is saved straight away. Writes that must
    # happen all-or-nothing use "with conn.transaction():" instead.
    # dict_row: rows come back as {"id": 1, "name": "Home"} instead of (1, "Home").
    conn = psycopg.connect(conninfo, autocommit=True, row_factory=dict_row)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)  # lets Python lists go in and out of vector columns
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS workspaces_name_lower ON workspaces (lower(name));

CREATE TABLE IF NOT EXISTS documents (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id bigint NOT NULL REFERENCES workspaces ON DELETE CASCADE,
    filename text NOT NULL,
    stored_path text NOT NULL,
    page_count int NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, filename)
);

CREATE TABLE IF NOT EXISTS chunks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES documents ON DELETE CASCADE,
    page int,
    text text NOT NULL,
    embedding vector(768) NOT NULL
);
"""


def init_db(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA)


# --- workspaces ---

def create_workspace(conn: psycopg.Connection, name: str) -> int:
    try:
        row = conn.execute(
            "INSERT INTO workspaces (name) VALUES (%s) RETURNING id", (name,)
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise AlreadyExists(f"A workspace called {name} already exists.") from None
    return row["id"]


def list_workspaces(conn: psycopg.Connection) -> list[dict]:
    return conn.execute(
        "SELECT id, name FROM workspaces ORDER BY lower(name)"
    ).fetchall()


def get_workspace(conn: psycopg.Connection, workspace_id: int) -> dict | None:
    return conn.execute(
        "SELECT id, name FROM workspaces WHERE id = %s", (workspace_id,)
    ).fetchone()


# --- documents ---

def document_exists(conn: psycopg.Connection, workspace_id: int, filename: str) -> bool:
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM documents WHERE workspace_id = %s AND filename = %s) AS found",
        (workspace_id, filename),
    ).fetchone()
    return row["found"]


def insert_document(
    conn: psycopg.Connection, workspace_id: int, filename: str, stored_path: str, page_count: int
) -> int:
    row = conn.execute(
        "INSERT INTO documents (workspace_id, filename, stored_path, page_count)"
        " VALUES (%s, %s, %s, %s) RETURNING id",
        (workspace_id, filename, stored_path, page_count),
    ).fetchone()
    return row["id"]


def insert_chunks(
    conn: psycopg.Connection, document_id: int, chunks: list[Chunk], embeddings: list[list[float]]
) -> None:
    rows = [
        (document_id, chunk.page, chunk.text, Vector(embedding))
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]
    with conn.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO chunks (document_id, page, text, embedding) VALUES (%s, %s, %s, %s)",
            rows,
        )


def list_documents(conn: psycopg.Connection, workspace_id: int) -> list[dict]:
    return conn.execute(
        "SELECT id, filename, page_count, created_at FROM documents"
        " WHERE workspace_id = %s ORDER BY lower(filename)",
        (workspace_id,),
    ).fetchall()


# --- searching ---

def count_chunks(conn: psycopg.Connection, workspace_id: int) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM chunks c"
        " JOIN documents d ON d.id = c.document_id"
        " WHERE d.workspace_id = %s",
        (workspace_id,),
    ).fetchone()
    return row["n"]


def search_chunks(
    conn: psycopg.Connection, workspace_id: int, embedding: list[float], limit: int
) -> list[dict]:
    # Exact search: measure the distance from the question to every chunk
    # in this workspace and keep the closest ones (0 = same meaning).
    return conn.execute(
        "SELECT d.filename, c.page, c.text, c.embedding <=> %s AS distance"
        " FROM chunks c JOIN documents d ON d.id = c.document_id"
        " WHERE d.workspace_id = %s"
        " ORDER BY distance LIMIT %s",
        (Vector(embedding), workspace_id, limit),
    ).fetchall()


# --- deleting ---

def delete_document(conn: psycopg.Connection, document_id: int) -> str | None:
    # Its chunks are deleted too (ON DELETE CASCADE).
    row = conn.execute(
        "DELETE FROM documents WHERE id = %s RETURNING stored_path", (document_id,)
    ).fetchone()
    return row["stored_path"] if row else None


def delete_workspace(conn: psycopg.Connection, workspace_id: int) -> list[str] | None:
    # Its documents and their chunks are deleted too (ON DELETE CASCADE).
    with conn.transaction():
        # FOR UPDATE locks the workspace row until we're done, so nobody can
        # add a document to it in between (its file would never be deleted).
        workspace = conn.execute(
            "SELECT id FROM workspaces WHERE id = %s FOR UPDATE", (workspace_id,)
        ).fetchone()
        if workspace is None:
            return None
        rows = conn.execute(
            "SELECT stored_path FROM documents WHERE workspace_id = %s", (workspace_id,)
        ).fetchall()
        conn.execute("DELETE FROM workspaces WHERE id = %s", (workspace_id,))
    return [row["stored_path"] for row in rows]