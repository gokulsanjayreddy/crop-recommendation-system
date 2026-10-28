"""Smoke tests for FastAPI endpoints, configuration, and mocked HTTP calls."""
import pytest
import httpx
from unittest.mock import patch, MagicMock
from backend.config import settings


def test_config_settings():
    """Verify that pydantic-settings loads expected default keys and timeouts."""
    assert settings.DATABASE_URL.startswith("sqlite:///") or "postgresql" in settings.DATABASE_URL
    assert settings.MODEL_DIR.exists()
    assert settings.DATA_DIR.exists()
    assert settings.HTTP_TIMEOUT > 0
    assert settings.OPEN_METEO_TIMEOUT > 0
    assert settings.NASA_POWER_TIMEOUT > 0
    assert settings.SOILGRIDS_TIMEOUT > 0


def test_get_meta(client):
    """Smoke test: GET /api/meta returns status 200 with soil_types, states, and crops."""
    response = client.get("/api/meta")
    assert response.status_code == 200
    data = response.json()

    assert "soil_types" in data
    assert "states" in data
    assert "crops" in data

    assert isinstance(data["soil_types"], list)
    assert len(data["soil_types"]) > 0
    assert "Black" in data["soil_types"]

    assert isinstance(data["states"], dict)
    assert "Maharashtra" in data["states"]

    assert isinstance(data["crops"], list)
    assert len(data["crops"]) == 20
    crop_names = [c["crop_name"] for c in data["crops"]]
    assert "Cotton" in crop_names


def test_post_recommend_sample(client):
    """Smoke test: POST /api/recommend with existing README sample payload."""
    payload = {
        "farmer_id": "F1023",
        "soil_type": "Black",
        "state": "Maharashtra",
        "district": "Nagpur",
        "previous_crop": "Cotton",
        "previous_outcome": "loss",
        "previous_profit_amount": -3200.0,
    }

    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "recommendations" in data
    assert "generated_at" in data

    recs = data["recommendations"]
    assert len(recs) == 3  # Top-3 recommendations

    for r in recs:
        assert "rank" in r
        assert "crop_name" in r
        assert "predicted_yield_ton_per_acre" in r
        assert "predicted_price_rs_per_quintal" in r
        assert "cost_of_cultivation_rs_per_acre" in r
        assert "predicted_profit_rs_per_acre" in r
        assert "reason" in r
        assert isinstance(r["reason"], str) and len(r["reason"]) > 0

    # Ensure recommendations are ranked in descending order of profit
    profits = [r["predicted_profit_rs_per_acre"] for r in recs]
    assert profits == sorted(profits, reverse=True)


def test_post_recommend_invalid_district(client):
    """POST /api/recommend with unknown district returns 404."""
    payload = {
        "farmer_id": "F1023",
        "soil_type": "Black",
        "state": "Maharashtra",
        "district": "NonExistentDistrict",
        "previous_crop": "Cotton",
        "previous_outcome": "loss",
        "previous_profit_amount": -1000.0,
    }
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 404
    assert "unknown district" in response.json()["detail"].lower()


def test_post_recommend_validation_error(client):
    """POST /api/recommend with invalid payload schema returns 422."""
    payload = {
        "farmer_id": "F1023",
        "soil_type": "Black",
        # missing state & district
        "previous_crop": "Cotton",
        "previous_outcome": "invalid_outcome",
    }
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 422


def test_mocked_http_client_pattern():
    """Verify mocked HTTP request pattern for public API integrations (Open-Meteo, NASA POWER, SoilGrids)."""
    mock_response = {
        "latitude": 16.5,
        "longitude": 80.5,
        "generationtime_ms": 0.1,
        "hourly": {"temperature_2m": [28.5, 29.0]},
    }

    def mock_transport_handler(request: httpx.Request) -> httpx.Response:
        if "open-meteo.com" in str(request.url):
            return httpx.Response(200, json=mock_response)
        return httpx.Response(404, json={"error": "Not mocked"})

    transport = httpx.MockTransport(mock_transport_handler)
    with httpx.Client(transport=transport, timeout=settings.HTTP_TIMEOUT) as http_client:
        resp = http_client.get("https://api.open-meteo.com/v1/forecast?latitude=16.5&longitude=80.5")
        assert resp.status_code == 200
        assert resp.json()["hourly"]["temperature_2m"] == [28.5, 29.0]
