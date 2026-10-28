"""Pytest fixtures and configuration for crop-recommendation-system."""
import pytest
from fastapi.testclient import TestClient
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
