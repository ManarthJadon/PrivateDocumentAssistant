import httpx

EMBED_BATCH = 32  # how many texts we send to Ollama in one request
NUM_CTX = 8192  # how much text the chat model can look at once (its "desk")
TEMPERATURE = 0.1  # low = steady, factual answers


# --- friendly errors (their text is shown to the user) ---

class OllamaError(Exception):
    """Something went wrong talking to Ollama."""


class OllamaUnavailable(OllamaError):
    def __init__(self):
        super().__init__("Ollama isn't running. Start it and try again.")


class ModelMissing(OllamaError):
    def __init__(self, model: str):
        super().__init__(f"Model {model} not found. Run: ollama pull {model}")


class OllamaTimeout(OllamaError):
    def __init__(self):
        super().__init__("The AI took too long. Try again.")


# --- the client ---

class OllamaClient:
    def __init__(
        self,
        base_url: str,
        embed_model: str,
        chat_model: str,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.embed_model = embed_model
        self.chat_model = chat_model
        # transport is only set by tests, to swap the real network for a pretend one.
        self.http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start:start + EMBED_BATCH]
            vectors += self._embed(["search_document: " + text for text in batch])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed(["search_query: " + text])[0]

    def chat(self, system: str, user: str) -> str:
        data = self._post(
            "/api/chat",
            {
                "model": self.chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"num_ctx": NUM_CTX, "temperature": TEMPERATURE},
            },
        )
        return data["message"]["content"]

    def _embed(self, inputs: list[str]) -> list[list[float]]:
        data = self._post("/api/embed", {"model": self.embed_model, "input": inputs})
        return data["embeddings"]

    def _post(self, path: str, body: dict) -> dict:
        # Send one request and turn network problems into friendly errors.
        try:
            response = self.http.post(path, json=body)
        except httpx.ConnectError as error:
            raise OllamaUnavailable() from error
        except httpx.TimeoutException as error:
            raise OllamaTimeout() from error

        if response.status_code == 404:
            raise ModelMissing(body["model"])
        response.raise_for_status()  # any other problem: a plain error (the app shows "Something went wrong.")
        return response.json()