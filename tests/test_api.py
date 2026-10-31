import pytest
from fastapi.testclient import TestClient

from app.ingest import MAX_BYTES
from app.main import app, get_conn, get_ollama, get_uploads_dir
from fakes import FakeOllama


@pytest.fixture
def fake():
    return FakeOllama()


@pytest.fixture
def client(conn, fake, tmp_path):
    # Swap the real database line, Ollama and uploads folder for test ones.
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_ollama] = lambda: fake
    app.dependency_overrides[get_uploads_dir] = lambda: tmp_path
    yield TestClient(app, base_url="http://127.0.0.1:8000")  # the same address the browser uses
    app.dependency_overrides.clear()


def make_workspace(client, name="College") -> int:
    return client.post("/api/workspaces", json={"name": name}).json()["id"]


def upload(client, workspace_id, filename="notes.txt", data=b"Apples are red."):
    return client.post(
        f"/api/workspaces/{workspace_id}/documents", files={"file": (filename, data)}
    )


# --- workspaces ---

def test_create_and_list_workspaces(client):
    response = client.post("/api/workspaces", json={"name": "  College  "})

    assert response.status_code == 201
    assert response.json()["name"] == "College"  # spaces around it are removed
    assert [w["name"] for w in client.get("/api/workspaces").json()] == ["College"]


def test_duplicate_workspace_is_409(client):
    make_workspace(client, "College")
    response = client.post("/api/workspaces", json={"name": "College"})

    assert response.status_code == 409
    assert response.json() == {"detail": "A workspace called College already exists."}


def test_workspace_name_differing_in_case_is_409(client):
    make_workspace(client, "College")
    assert client.post("/api/workspaces", json={"name": "college"}).status_code == 409


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_bad_workspace_name_is_400(client, name):
    response = client.post("/api/workspaces", json={"name": name})

    assert response.status_code == 400
    assert response.json() == {"detail": "Please enter a name (max 100 characters)."}


# --- uploading ---

def test_upload_txt_is_listed(client):
    workspace_id = make_workspace(client)
    response = upload(client, workspace_id)

    assert response.status_code == 201
    assert response.json()["filename"] == "notes.txt"
    documents = client.get(f"/api/workspaces/{workspace_id}/documents").json()
    assert [d["filename"] for d in documents] == ["notes.txt"]


def test_upload_wrong_type_is_400(client):
    response = upload(client, make_workspace(client), "a.exe", b"whatever")

    assert response.status_code == 400
    assert response.json() == {"detail": "Only .pdf, .docx, .txt and .md files are supported."}


def test_upload_too_big_is_413(client):
    response = upload(client, make_workspace(client), "big.txt", b"a" * (MAX_BYTES + 1))

    assert response.status_code == 413
    assert response.json() == {"detail": "File is too big (max 20 MB)."}


def test_upload_duplicate_is_409(client):
    workspace_id = make_workspace(client)
    upload(client, workspace_id)
    response = upload(client, workspace_id)

    assert response.status_code == 409
    assert response.json() == {"detail": "notes.txt is already in this workspace."}


def test_upload_to_unknown_workspace_is_404(client):
    response = upload(client, 999)

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found."}


# --- asking ---

def test_ask_returns_answer_and_sources(client, fake):
    workspace_id = make_workspace(client)
    upload(client, workspace_id, "apples.txt", b"Apples are red.")
    fake.reply = "They are red [1]."

    response = client.post(f"/api/workspaces/{workspace_id}/ask", json={"question": "Are apples red?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "They are red [1]."
    assert body["sources"][0]["filename"] == "apples.txt"
    assert body["related"] is False


@pytest.mark.parametrize("question", ["", "   ", "x" * 2001])
def test_bad_question_is_400(client, question):
    response = client.post(f"/api/workspaces/{make_workspace(client)}/ask", json={"question": question})

    assert response.status_code == 400
    assert response.json() == {"detail": "Please type a question (max 2000 characters)."}


def test_ask_when_ollama_is_down_is_503(client, fake):
    workspace_id = make_workspace(client)
    upload(client, workspace_id)
    fake.down = True

    response = client.post(f"/api/workspaces/{workspace_id}/ask", json={"question": "Are apples red?"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Ollama isn't running. Start it and try again."}


# --- deleting ---

def test_delete_document_removes_file(client, tmp_path):
    workspace_id = make_workspace(client)
    document_id = upload(client, workspace_id).json()["id"]
    assert len(list(tmp_path.iterdir())) == 1

    assert client.delete(f"/api/documents/{document_id}").status_code == 204
    assert client.get(f"/api/workspaces/{workspace_id}/documents").json() == []
    assert list(tmp_path.iterdir()) == []


def test_delete_document_with_missing_file_still_works(client, tmp_path):
    workspace_id = make_workspace(client)
    document_id = upload(client, workspace_id).json()["id"]
    for file in tmp_path.iterdir():
        file.unlink()  # someone already removed the file by hand

    assert client.delete(f"/api/documents/{document_id}").status_code == 204


def test_delete_workspace_removes_files(client, tmp_path):
    workspace_id = make_workspace(client)
    upload(client, workspace_id, "a.txt", b"Apples.")
    upload(client, workspace_id, "b.txt", b"Bananas.")

    assert client.delete(f"/api/workspaces/{workspace_id}").status_code == 204
    assert client.get("/api/workspaces").json() == []
    assert list(tmp_path.iterdir()) == []


def test_delete_unknown_is_404(client):
    assert client.delete("/api/documents/999").status_code == 404
    assert client.delete("/api/workspaces/999").status_code == 404


# --- safety ---

def test_unknown_host_is_rejected(client):
    # A website pretending to be this computer (DNS rebinding) must not get any data.
    response = client.get("/api/workspaces", headers={"Host": "evil.example"})

    assert response.status_code == 400

@pytest.mark.parametrize("origin", ["https://evil.example", "http://127.0.0.1:9999", "null"])
def test_other_website_cannot_write(client, origin):
    workspace_id = make_workspace(client)
    headers = {"Origin": origin}

    response = client.post(
        f"/api/workspaces/{workspace_id}/documents",
        files={"file": ("notes.txt", b"Apples are red.")},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "This request came from another website."}
    assert client.get(f"/api/workspaces/{workspace_id}/documents").json() == []  # nothing was saved
    assert client.delete(f"/api/workspaces/{workspace_id}", headers=headers).status_code == 403


@pytest.mark.parametrize("headers", [
    {},  # curl and other tools send no Origin
    {"Origin": "http://127.0.0.1:8000"},
    {"Origin": "http://localhost:8000"},
])
def test_this_computer_can_write(client, headers):
    workspace_id = make_workspace(client)

    response = client.post(
        f"/api/workspaces/{workspace_id}/documents",
        files={"file": ("notes.txt", b"Apples are red.")},
        headers=headers,
    )

    assert response.status_code == 201


# --- web page ---

def test_index_is_served(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")