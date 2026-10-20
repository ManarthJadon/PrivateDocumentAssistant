import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row


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