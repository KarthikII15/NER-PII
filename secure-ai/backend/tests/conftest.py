"""
conftest.py — Shared pytest fixtures for unit and integration tests.
"""
import os
import pytest
from fastapi.testclient import TestClient

# Ensure required env vars are set before importing the app
os.environ.setdefault("API_KEY", "test-key-for-ci")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DB_PATH", "/tmp/test_audit.db")
os.environ.setdefault("UPLOAD_DIR", "/tmp/uploads")
os.environ.setdefault("PROCESSED_DIR", "/tmp/processed")
os.environ.setdefault("SIGNED_DIR", "/tmp/signed")
os.environ.setdefault("KEYS_DIR", "/tmp/keys")


@pytest.fixture(scope="module")
def client():
    """Return a FastAPI test client with the app loaded."""
    from app.main import app
    with TestClient(app) as c:
        yield c
