from pathlib import Path

from app.config import get_settings


def test_get_settings_reads_env(monkeypatch):
    # Arrange: pretend these settings are in the environment
    monkeypatch.setenv("POSTGRES_DB", "x")
    monkeypatch.setenv("POSTGRES_PORT", "5999")
    monkeypatch.setenv("UPLOADS_DIR", "tmpdir")
    monkeypatch.delenv("CHAT_MODEL", raising=False)

    # Act: read the settings
    settings = get_settings()

    # Assert: our values are used, and missing ones get their defaults
    assert "dbname=x" in settings.db_conninfo
    assert "port=5999" in settings.db_conninfo
    assert settings.uploads_dir == Path("tmpdir")
    assert settings.chat_model == "llama3.1:8b"