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


def test_get_history_seeded_farmer(client):
    """GET /api/history/{farmer_id} returns 200 with seeded history logs from CSV."""
    response = client.get("/api/history/F1001")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

    first_log = data[0]
    assert first_log["farmer_id"] == "F1001"
    assert "id" in first_log
    assert "season" in first_log
    assert "year" in first_log
    assert "soil_type" in first_log
    assert "outcome" in first_log
    assert "next_crop_sown" in first_log


def test_get_history_unknown_farmer(client):
    """GET /api/history/{farmer_id} for unknown farmer returns empty list."""
    response = client.get("/api/history/UNKNOWN_FARMER_999")
    assert response.status_code == 200
    assert response.json() == []


def test_post_and_get_history_log_season(client):
    """POST /api/history creates a new season log, verified by subsequent GET."""
    import uuid
    new_farmer_id = f"F_TEST_{uuid.uuid4().hex[:6]}"
    payload = {
        "farmer_id": new_farmer_id,
        "farmer_name": "Rao Bahadur",
        "location_id": 10,
        "season": "Kharif",
        "year": 2024,
        "soil_type": "Black",
        "previous_crop": "Cotton",
        "outcome": "profit",
        "profit_amount_rs_per_acre": 9200.0,
        "next_crop_sown": "Soybean",
    }

    post_resp = client.post("/api/history", json=payload)
    assert post_resp.status_code == 200
    created = post_resp.json()
    assert created["farmer_id"] == new_farmer_id
    assert created["id"] > 0
    assert created["outcome"] == "profit"
    assert created["profit_amount_rs_per_acre"] == 9200.0

    # Retrieve and verify persistence
    get_resp = client.get(f"/api/history/{new_farmer_id}")
    assert get_resp.status_code == 200
    logs = get_resp.json()
    assert len(logs) == 1
    assert logs[0]["id"] == created["id"]
    assert logs[0]["farmer_name"] == "Rao Bahadur"
    assert logs[0]["next_crop_sown"] == "Soybean"


def test_database_url_resolution_and_engine():
    """Verify DATABASE_URL resolution, Postgres dialect setup and SQLite fallback."""
    import os
    import sys
    from backend.db import create_db_engine, resolve_database_url, _normalize_db_url, DEFAULT_POSTGRES_URL

    # Test normalization of legacy postgres:// scheme
    assert _normalize_db_url("postgres://user:pass@host/db") == "postgresql://user:pass@host/db"
    assert _normalize_db_url("postgresql://user:pass@host/db") == "postgresql://user:pass@host/db"

    # SQLite engine creation
    sqlite_engine = create_db_engine("sqlite:///:memory:")
    assert sqlite_engine.dialect.name == "sqlite"

    # PostgreSQL engine creation with psycopg2 dialect
    pg_engine = create_db_engine("postgresql://postgres:postgres@localhost:5432/crop_db")
    assert pg_engine.dialect.name == "postgresql"
    assert pg_engine.dialect.driver == "psycopg2"

    # Test fallback behavior when no DATABASE_URL is set in test environment
    original_env = os.environ.get("DATABASE_URL")
    try:
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        resolved = resolve_database_url()
        # In pytest, it should resolve to the SQLite fallback
        assert resolved.startswith("sqlite:")
    finally:
        if original_env is not None:
            os.environ["DATABASE_URL"] = original_env


def test_season_log_schema_ddl_compatibility():
    """Verify SeasonLog DDL compiles for both SQLite and PostgreSQL dialects (SQLAlchemy 2)."""
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import postgresql, sqlite
    from backend.db import SeasonLog

    # Compile table DDL for PostgreSQL
    pg_ddl = str(CreateTable(SeasonLog.__table__).compile(dialect=postgresql.dialect()))
    assert "CREATE TABLE season_logs" in pg_ddl
    assert "farmer_id VARCHAR(32)" in pg_ddl
    assert "location_id INTEGER" in pg_ddl

    # Compile table DDL for SQLite
    sqlite_ddl = str(CreateTable(SeasonLog.__table__).compile(dialect=sqlite.dialect()))
    assert "CREATE TABLE season_logs" in sqlite_ddl
    assert "farmer_id VARCHAR(32)" in sqlite_ddl


def test_seed_from_csv_idempotency():
    """Verify seed_from_csv idempotently loads data into an engine."""
    from backend.db import create_db_engine, Base, SeasonLog
    from backend.routers.history import seed_from_csv
    from sqlalchemy.orm import sessionmaker

    test_engine = create_db_engine("sqlite:///:memory:")
    test_session = sessionmaker(bind=test_engine, autoflush=False)

    # First seed
    seed_from_csv(target_engine=test_engine, session_factory=test_session)
    with test_session() as session:
        initial_count = session.query(SeasonLog).count()
        assert initial_count > 0

    # Second seed should be a no-op (idempotent)
    seed_from_csv(target_engine=test_engine, session_factory=test_session)
    with test_session() as session:
        second_count = session.query(SeasonLog).count()
        assert second_count == initial_count


def test_mocked_http_nasa_power_and_soilgrids():
    """Verify mocked HTTP calls for NASA POWER and ISRIC SoilGrids APIs."""
    nasa_data = {
        "properties": {
            "parameter": {
                "T2M": {"20240101": 24.5, "20240102": 25.1},
                "PRECTOTCORR": {"20240101": 0.0, "20240102": 1.2},
            }
        }
    }
    soilgrids_data = {
        "properties": {
            "layers": [
                {"name": "phh2o", "depths": [{"label": "0-5cm", "values": {"mean": 68}}]},
                {"name": "soc", "depths": [{"label": "0-5cm", "values": {"mean": 120}}]},
            ]
        }
    }

    def mock_transport_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "power.larc.nasa.gov" in url_str:
            return httpx.Response(200, json=nasa_data)
        elif "rest.isric.org" in url_str:
            return httpx.Response(200, json=soilgrids_data)
        return httpx.Response(404, json={"error": "Not mocked"})

    transport = httpx.MockTransport(mock_transport_handler)
    with httpx.Client(transport=transport, timeout=settings.HTTP_TIMEOUT) as http_client:
        nasa_resp = http_client.get(
            "https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M,PRECTOTCORR&community=AG&longitude=80.5&latitude=16.5&start=20240101&end=20240102&format=JSON"
        )
        assert nasa_resp.status_code == 200
        assert nasa_resp.json()["properties"]["parameter"]["T2M"]["20240101"] == 24.5

        soil_resp = http_client.get(
            "https://rest.isric.org/soilgrids/v2.0/properties/query?lon=80.5&lat=16.5&property=phh2o&property=soc"
        )
        assert soil_resp.status_code == 200
        layers = soil_resp.json()["properties"]["layers"]
        assert len(layers) == 2
        assert layers[0]["name"] == "phh2o"
