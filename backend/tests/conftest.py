# Shared pytest fixtures for the backend test suite.
#
# Semantic writes to Fuseki are disabled by default so ingest-driven tests
# never make real network calls. Tests that specifically exercise the
# semantic trigger re-enable it via monkeypatch.
import pytest


@pytest.fixture(autouse=True)
def _disable_semantic_write(monkeypatch):
    monkeypatch.setattr("backend.config.SEMANTIC_WRITE_ENABLED", False)
