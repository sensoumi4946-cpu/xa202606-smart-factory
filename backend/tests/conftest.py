# Shared pytest fixtures for the backend test suite.

import pytest


@pytest.fixture(autouse=True)
def _disable_semantic_write(monkeypatch):
    monkeypatch.setattr("backend.config.SEMANTIC_WRITE_ENABLED", False)


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    monkeypatch.setattr("backend.security.auth._AUTH_DISABLED", True)