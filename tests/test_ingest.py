import pytest

from app import db
from app.db import AlreadyExists, NotFound, create_workspace, list_documents
from app.ingest import MAX_BYTES, FileTooBig, add_document
from app.ollama_client import OllamaUnavailable
from app.reader import ReadError
from fakes import FakeOllama

LONG_TEXT = b"Apples are red. " * 200  # about 3200 characters: several chunks


@pytest.fixture
def workspace_id(conn):
    return create_workspace(conn, "College")


def chunk_rows(conn) -> int:
    return conn.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"]


# --- the happy path ---

def test_add_txt_saves_rows_and_file(conn, workspace_id, tmp_path):
    add_document(conn, FakeOllama(), tmp_path, workspace_id, "notes.txt", b"Apples are red.")

    assert [doc["filename"] for doc in list_documents(conn, workspace_id)] == ["notes.txt"]
    assert chunk_rows(conn) > 0
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".txt"
    assert files[0].name != "notes.txt"  # saved under a random name


def test_folder_parts_are_stripped(conn, workspace_id, tmp_path):
    add_document(conn, FakeOllama(), tmp_path, workspace_id, "C:\\fakepath\\notes.txt", b"Apples.")
    add_document(conn, FakeOllama(), tmp_path, workspace_id, "../../evil.txt", b"Bananas.")

    names = [doc["filename"] for doc in list_documents(conn, workspace_id)]
    assert names == ["evil.txt", "notes.txt"]


def test_chunk_size_can_change(conn, workspace_id, tmp_path):
    add_document(conn, FakeOllama(), tmp_path, workspace_id, "notes.txt", LONG_TEXT, chunk_size=500)

    longest = conn.execute("SELECT max(length(text)) AS n FROM chunks").fetchone()["n"]
    assert longest <= 500


# --- refused early: nothing is embedded or saved ---

def test_too_big_saves_nothing(conn, workspace_id, tmp_path):
    ollama = FakeOllama()
    with pytest.raises(FileTooBig):
        add_document(conn, ollama, tmp_path, workspace_id, "big.txt", b"a" * (MAX_BYTES + 1))

    assert ollama.embed_calls == 0
    assert list(tmp_path.iterdir()) == []


def test_unknown_workspace_raises_not_found(conn, tmp_path):
    with pytest.raises(NotFound):
        add_document(conn, FakeOllama(), tmp_path, 999, "notes.txt", b"Apples.")


def test_duplicate_raises_before_embedding(conn, workspace_id, tmp_path):
    ollama = FakeOllama()
    add_document(conn, ollama, tmp_path, workspace_id, "notes.txt", b"Apples are red.")
    calls_before = ollama.embed_calls

    with pytest.raises(AlreadyExists, match="notes.txt is already in this workspace."):
        add_document(conn, ollama, tmp_path, workspace_id, "notes.txt", b"Apples are red.")

    assert ollama.embed_calls == calls_before


def test_unreadable_file_saves_nothing(conn, workspace_id, tmp_path):
    with pytest.raises(ReadError):
        add_document(conn, FakeOllama(), tmp_path, workspace_id, "a.exe", b"whatever")

    assert list(tmp_path.iterdir()) == []


# --- failing halfway: everything is undone ---

def test_embedding_failure_leaves_nothing(conn, workspace_id, tmp_path):
    ollama = FakeOllama()
    ollama.fail_after = 1  # Ollama "crashes" after the first chunk

    with pytest.raises(OllamaUnavailable):
        add_document(conn, ollama, tmp_path, workspace_id, "long.txt", LONG_TEXT)

    assert list_documents(conn, workspace_id) == []
    assert list(tmp_path.iterdir()) == []


def test_database_failure_deletes_file(conn, workspace_id, tmp_path, monkeypatch):
    def broken_insert_chunks(*args):
        raise RuntimeError("the database broke")

    monkeypatch.setattr(db, "insert_chunks", broken_insert_chunks)

    with pytest.raises(RuntimeError):
        add_document(conn, FakeOllama(), tmp_path, workspace_id, "notes.txt", b"Apples are red.")

    assert list_documents(conn, workspace_id) == []  # the document row was undone too
    assert list(tmp_path.iterdir()) == []