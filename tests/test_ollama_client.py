import json
import math

import httpx
import pytest

from app.ollama_client import ModelMissing, OllamaClient, OllamaTimeout, OllamaUnavailable
from fakes import FakeOllama


def make_client(handler) -> OllamaClient:
    # A client whose "internet" is the handler function, not the real Ollama.
    return OllamaClient(
        "http://ollama.test",
        "nomic-embed-text",
        "llama3.1:8b",
        transport=httpx.MockTransport(handler),
    )


# --- the real client, talking to a pretend Ollama ---

def test_embed_documents_adds_prefix_and_batches():
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        vectors = [[0.0] * 768 for _ in body["input"]]
        return httpx.Response(200, json={"embeddings": vectors})

    vectors = make_client(handler).embed_documents([f"t{i}" for i in range(40)])

    assert len(requests) == 2  # 40 texts = one batch of 32 + one batch of 8
    assert len(requests[0]["input"]) == 32
    assert requests[0]["input"][0] == "search_document: t0"
    assert len(vectors) == 40


def test_embed_query_adds_prefix():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"embeddings": [[0.5] * 768]})

    vector = make_client(handler).embed_query("what colour are apples?")

    assert requests[0]["input"] == ["search_query: what colour are apples?"]
    assert len(vector) == 768


def test_connection_error_raises_unavailable():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(OllamaUnavailable, match="Ollama isn't running"):
        make_client(handler).embed_query("hi")


def test_timeout_raises_timeout():
    def handler(request):
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(OllamaTimeout, match="The AI took too long"):
        make_client(handler).embed_query("hi")


def test_404_raises_model_missing():
    def handler(request):
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(ModelMissing) as caught:
        make_client(handler).embed_query("hi")
    assert str(caught.value) == "Model nomic-embed-text not found. Run: ollama pull nomic-embed-text"


# --- chat ---

def test_chat_sends_num_ctx_and_temperature():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        reply = {"message": {"role": "assistant", "content": "Apples are red [1]."}}
        return httpx.Response(200, json=reply)

    answer = make_client(handler).chat("Only use the excerpts.", "What colour are apples?")

    body = requests[0]
    assert body["model"] == "llama3.1:8b"
    assert body["stream"] is False
    assert body["options"] == {"num_ctx": 8192, "temperature": 0.1}
    assert body["messages"] == [
        {"role": "system", "content": "Only use the excerpts."},
        {"role": "user", "content": "What colour are apples?"},
    ]
    assert answer == "Apples are red [1]."


def test_chat_turns_thinking_off_for_qwen3():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "Red [1]."}})

    qwen = OllamaClient(
        "http://ollama.test", "nomic-embed-text", "qwen3:8b", transport=httpx.MockTransport(handler)
    )
    qwen.chat("Only use the excerpts.", "What colour are apples?")
    make_client(handler).chat("Only use the excerpts.", "What colour are apples?")  # llama3.1:8b

    assert requests[0]["think"] is False  # qwen3: thinking switched off
    assert "think" not in requests[1]     # llama: request unchanged

# --- the fake Ollama used by later tests ---

def cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return 1 - dot / (math.hypot(*a) * math.hypot(*b))


def test_fake_similar_texts_are_closer():
    apples, red_apples, stocks = FakeOllama().embed_documents(
        ["apples are red", "red apples", "stock market"]
    )
    assert cosine_distance(apples, red_apples) < cosine_distance(apples, stocks)