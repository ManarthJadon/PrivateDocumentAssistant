import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo


@dataclass(frozen=True)
class Settings:
    db_conninfo: str
    ollama_url: str
    embed_model: str
    chat_model: str
    uploads_dir: Path


def get_settings() -> Settings:
    # Read .env into the environment. Variables that are already set win,
    # so tests and Docker can override anything in .env.
    load_dotenv()

    db_conninfo = make_conninfo(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=os.getenv("POSTGRES_PORT", "5433"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    return Settings(
        db_conninfo=db_conninfo,
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text"),
        chat_model=os.getenv("CHAT_MODEL", "llama3.1:8b"),
        uploads_dir=Path(os.getenv("UPLOADS_DIR", "uploads")),
    )