import pytest

from app.chunker import Chunk
from app.db import (
    AlreadyExists,
    clear_questions,
    count_chunks,
    create_workspace,
    delete_document,
    delete_workspace,
    get_workspace,
    init_db,
    insert_chunks,
    insert_document,
    insert_question,
    list_documents,
    list_questions,
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


def test_duplicate_document_raises(conn):
    # Two uploads of the same file at once both pass the "already there?" check;
    # the database's UNIQUE rule must then turn into a friendly error, not a crash.
    workspace_id = create_workspace(conn, "College")
    insert_document(conn, workspace_id, "notes.txt", "a.txt", 1)
    with pytest.raises(AlreadyExists, match="notes.txt is already in this workspace."):
        insert_document(conn, workspace_id, "notes.txt", "b.txt", 1)


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


# --- past questions ---

SOURCE = {"number": 1, "filename": "notes.txt", "page": None, "text": "Apples are red."}


def all_question_rows(conn) -> int:
    return conn.execute("SELECT count(*) AS n FROM questions").fetchone()["n"]


def test_insert_and_list_questions_newest_first(conn):
    workspace_id = create_workspace(conn, "College")
    insert_question(conn, workspace_id, "First?", "Red [1].", [SOURCE], False)
    insert_question(conn, workspace_id, "Second?", "Some passages.", [], True)

    rows = list_questions(conn, workspace_id)
    assert [row["question"] for row in rows] == ["Second?", "First?"]  # newest first
    assert rows[1]["sources"] == [SOURCE]  # sources come back exactly as saved
    assert rows[0]["related"] is True


def test_list_questions_keeps_latest_50(conn):
    workspace_id = create_workspace(conn, "College")
    for i in range(51):
        insert_question(conn, workspace_id, f"Q{i}", "A", [], False)

    rows = list_questions(conn, workspace_id)
    assert len(rows) == 50
    assert rows[0]["question"] == "Q50"  # the oldest one (Q0) is the one left out


def test_clear_questions_only_clears_that_workspace(conn):
    a = create_workspace(conn, "A")
    b = create_workspace(conn, "B")
    insert_question(conn, a, "A?", "x", [], False)
    insert_question(conn, b, "B?", "x", [], False)

    clear_questions(conn, a)
    assert list_questions(conn, a) == []
    assert len(list_questions(conn, b)) == 1


def test_delete_workspace_deletes_its_questions(conn):
    workspace_id = create_workspace(conn, "College")
    insert_question(conn, workspace_id, "Q?", "A", [], False)

    delete_workspace(conn, workspace_id)
    assert all_question_rows(conn) == 0


def test_delete_document_deletes_questions_that_quote_it(conn):
    workspace_id = create_workspace(conn, "College")
    name = 'केले "v2".txt'  # Hindi and quotes: the search must still find it
    document_id = add_document_row(conn, workspace_id, name, "a.txt")
    insert_question(conn, workspace_id, "Quotes it?", "x [1]", [{**SOURCE, "filename": name}], False)
    insert_question(conn, workspace_id, "Other?", "x [1]", [{**SOURCE, "filename": "other.txt"}], False)
    insert_question(conn, workspace_id, "No sources?", "Not found.", [], False)

    delete_document(conn, document_id)
    remaining = [row["question"] for row in list_questions(conn, workspace_id)]
    assert remaining == ["No sources?", "Other?"]


def test_delete_document_keeps_other_workspaces_history(conn):
    a = create_workspace(conn, "A")
    b = create_workspace(conn, "B")
    document_id = add_document_row(conn, a, "notes.txt", "a.txt")
    insert_question(conn, b, "B?", "x [1]", [SOURCE], False)  # B also has a notes.txt answer

    delete_document(conn, document_id)
    assert len(list_questions(conn, b)) == 1