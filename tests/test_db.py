import pytest

from app.chunker import Chunk
from app.db import (
    AlreadyExists,
    count_chunks,
    create_workspace,
    delete_document,
    delete_workspace,
    get_workspace,
    init_db,
    insert_chunks,
    insert_document,
    list_documents,
    list_workspaces,
)


# --- creating the tables ---

def test_init_db_twice_is_safe(conn):
    # The fixture already ran init_db once; a second run must not fail.
    # (The app runs it on every start, so this happens all the time.)
    init_db(conn)


# --- workspaces ---

def test_create_and_list_workspaces(conn):
    home_id = create_workspace(conn, "Home")
    create_workspace(conn, "College")

    names = [workspace["name"] for workspace in list_workspaces(conn)]
    assert names == ["College", "Home"]  # sorted by name, not by creation order
    assert get_workspace(conn, home_id)["name"] == "Home"


def test_duplicate_name_raises(conn):
    create_workspace(conn, "College")
    with pytest.raises(AlreadyExists, match="A workspace called College already exists."):
        create_workspace(conn, "College")


def test_name_differing_only_in_case_is_duplicate(conn):
    create_workspace(conn, "College")
    with pytest.raises(AlreadyExists):
        create_workspace(conn, "college")


def test_get_missing_workspace_returns_none(conn):
    assert get_workspace(conn, 999) is None


# --- deleting ---

def add_document_row(conn, workspace_id: int, filename: str, stored_path: str) -> int:
    # A document with one chunk, saved straight into the database (no file, no AI).
    document_id = insert_document(conn, workspace_id, filename, stored_path, 1)
    insert_chunks(conn, document_id, [Chunk(None, "Some text")], [[0.1] * 768])
    return document_id


def all_chunk_rows(conn) -> int:
    return conn.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"]


def test_delete_document_cascades_and_returns_path(conn):
    workspace_id = create_workspace(conn, "College")
    document_id = add_document_row(conn, workspace_id, "notes.txt", "abc123.txt")

    assert delete_document(conn, document_id) == "abc123.txt"
    assert list_documents(conn, workspace_id) == []
    assert count_chunks(conn, workspace_id) == 0  # its chunks went too


def test_delete_workspace_returns_paths_and_cascades(conn):
    workspace_id = create_workspace(conn, "College")
    add_document_row(conn, workspace_id, "a.txt", "aaa.txt")
    add_document_row(conn, workspace_id, "b.pdf", "bbb.pdf")

    assert sorted(delete_workspace(conn, workspace_id)) == ["aaa.txt", "bbb.pdf"]
    assert get_workspace(conn, workspace_id) is None
    assert all_chunk_rows(conn) == 0  # documents and chunks went too


def test_delete_missing_returns_none(conn):
    assert delete_document(conn, 999) is None
    assert delete_workspace(conn, 999) is None