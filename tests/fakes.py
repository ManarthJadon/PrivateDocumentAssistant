import re
import zlib

from app.ollama_client import OllamaUnavailable


class FakeOllama:
    """Stands in for OllamaClient in tests: instant, offline and predictable."""

    def __init__(self):
        # Settings a test can change:
        self.reply = "Fake answer [1]."  # what chat() answers
        self.fail_after = None  # e.g. 3: act like Ollama crashes after 3 texts were embedded
        self.down = False  # True: act like Ollama isn't running at all

        # Counters a test can check afterwards:
        self.embed_calls = 0
        self.chat_calls = 0
        self.last_user_prompt = None
        self.texts_embedded = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.down:
            raise OllamaUnavailable()
        self.embed_calls += 1
        self.texts_embedded += len(texts)
        if self.fail_after is not None and self.texts_embedded > self.fail_after:
            raise OllamaUnavailable()
        return [make_vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def chat(self, system: str, user: str) -> str:
        if self.down:
            raise OllamaUnavailable()
        self.chat_calls += 1
        self.last_user_prompt = user
        return self.reply


def make_vector(text: str) -> list[float]:
    # 768 numbers, like nomic-embed-text. Every word gets its own slot
    # and adds 1 there, so texts that share words point in similar directions.
    vector = [0.0] * 768
    vector[0] = 0.1  # never all zeros: an all-zero arrow has no direction
    for word in re.findall(r"\w+", text.lower()):
        vector[zlib.crc32(word.encode()) % 767 + 1] += 1
    return vector