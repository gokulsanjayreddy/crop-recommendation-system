"""Pytest fixtures and configuration for crop-recommendation-system."""
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure test suite uses SQLite fallback by default unless DATABASE_URL was explicitly provided
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = f"sqlite:///{(BACKEND_DIR / 'app.db').as_posix()}"

from backend.main import app
from backend.config import Settings, get_settings


@pytest.fixture(scope="session")
def client():
    """FastAPI TestClient fixture with app lifecycle."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def test_settings():
    """Settings instance for test inspections."""
    return get_settings()
