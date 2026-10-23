import pytest

from app.db import NotFound, create_workspace
from app.ingest import add_document
from app.rag import EMPTY_MESSAGE, NOT_FOUND_MESSAGE, ask, build_prompt, parse_answer
from fakes import FakeOllama

CHUNKS = [
    {"filename": "a.pdf", "page": 4, "text": "A text", "distance": 0.1},
    {"filename": "b.docx", "page": None, "text": "B text", "distance": 0.2},
]


# --- building the prompt ---

def test_build_prompt_format():
    assert build_prompt("Q", CHUNKS) == (
        "Excerpts:\n"
        "[1] (a.pdf, page 4)\nA text\n\n"
        "[2] (b.docx)\nB text\n\n"
        "Question: Q"
    )


# --- reading the reply ---

def test_parse_not_found():
    for reply in ["NOT_FOUND", "NOT_FOUND.", "  NOT_FOUND\n"]:
        answer = parse_answer(reply, CHUNKS)
        assert answer.text == NOT_FOUND_MESSAGE
        assert answer.sources == []


def test_parse_keeps_valid_ignores_invalid():
    answer = parse_answer("A [2] B [7] C [2]", CHUNKS)
    # [7] doesn't exist and [2] is only listed once.
    assert answer.sources == [{"number": 2, "filename": "b.docx", "page": None, "text": "B text"}]
    assert answer.related is False


def test_parse_no_citations_is_related():
    answer = parse_answer("Some answer without numbers.", CHUNKS)
    assert [source["number"] for source in answer.sources] == [1, 2]
    assert answer.related is True


# --- the whole question flow ---

def test_ask_unknown_workspace_raises_not_found(conn):
    with pytest.raises(NotFound):
        ask(conn, FakeOllama(), 999, "What colour are apples?")


def test_ask_empty_workspace_skips_ai(conn):
    ollama = FakeOllama()
    workspace_id = create_workspace(conn, "College")

    answer = ask(conn, ollama, workspace_id, "What colour are apples?")

    assert answer.text == EMPTY_MESSAGE
    assert ollama.embed_calls == 0
    assert ollama.chat_calls == 0


def test_ask_far_chunks_is_not_found(conn, tmp_path):
    ollama = FakeOllama()
    workspace_id = create_workspace(conn, "College")
    add_document(conn, ollama, tmp_path, workspace_id, "apples.txt", b"Apples are red.")

    # A cutoff of -1 means even a perfect match counts as "too far".
    answer = ask(conn, ollama, workspace_id, "What colour are apples?", max_distance=-1)

    assert answer.text == NOT_FOUND_MESSAGE
    assert ollama.chat_calls == 0


def test_ask_returns_cited_source(conn, tmp_path):
    ollama = FakeOllama()
    ollama.reply = "They are red [1]."
    workspace_id = create_workspace(conn, "College")
    add_document(conn, ollama, tmp_path, workspace_id, "apples.txt", b"Apples are red.")

    # A cutoff of 2 means nothing is ever "too far", so the AI is always asked.
    answer = ask(conn, ollama, workspace_id, "What colour are apples?", max_distance=2)

    assert answer.text == "They are red [1]."
    assert answer.sources[0]["filename"] == "apples.txt"
    assert answer.related is False


def test_ask_only_searches_its_workspace(conn, tmp_path):
    ollama = FakeOllama()
    college = create_workspace(conn, "College")
    home = create_workspace(conn, "Home")
    add_document(conn, ollama, tmp_path, college, "apples.txt", b"Apples are red.")
    add_document(conn, ollama, tmp_path, home, "bananas.txt", b"Bananas are yellow.")

    answer = ask(conn, ollama, home, "What colour are apples?", max_distance=2)

    assert all(source["filename"] != "apples.txt" for source in answer.sources)
    assert "Apples" not in ollama.last_user_prompt