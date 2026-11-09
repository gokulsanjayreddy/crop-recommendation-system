"""Tests for /api/live-weather and the Open-Meteo service.

All outbound HTTP is mocked; no test touches the live provider.
"""
from datetime import datetime

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import weather as weather_router
from backend.services import weather


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", weather.OPEN_METEO_FORECAST_URL)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def sample_payload():
    return {
        "latitude": 16.25,
        "longitude": 81.0,
        "timezone": "Asia/Kolkata",
        "current": {
            "time": "2026-11-09T23:15",
            "temperature_2m": 28.4,
            "relative_humidity_2m": 72,
            "precipitation": 0.2,
        },
        "daily": {
            "time": ["2026-11-08", "2026-11-09", "2026-11-10"],
            "temperature_2m_max": [31.2, 30.8, 31.5],
            "temperature_2m_min": [21.4, 21.0, 21.8],
            "precipitation_sum": [0.0, 2.4, 0.0],
        },
    }


@pytest.fixture(autouse=True)
def clean_cache():
    weather.clear_cache()
    yield
    weather.clear_cache()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(weather_router.router)
    return TestClient(app)


def install_fake_http(monkeypatch, payload=None, status_code=200):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        return FakeResponse(
            sample_payload() if payload is None else payload, status_code=status_code
        )

    monkeypatch.setattr(weather.httpx, "get", fake_get)
    return calls


def test_district_request_and_parsing(monkeypatch):
    calls = install_fake_http(monkeypatch)

    response = weather.get_live_weather(district="krishna")

    assert response.location == "Krishna"
    assert response.district == "Krishna"
    assert response.source == "open-meteo"
    assert response.timezone == "Asia/Kolkata"
    assert response.current.temperature_c == 28.4
    assert response.current.humidity_pct == 72
    assert response.current.precipitation_mm == 0.2
    assert [day.date for day in response.daily] == [
        "2026-11-08",
        "2026-11-09",
        "2026-11-10",
    ]
    assert response.daily[1].temperature_max_c == 30.8
    assert response.daily[1].temperature_min_c == 21.0
    assert response.daily[1].precipitation_mm == 2.4
    assert datetime.fromisoformat(response.fetched_at).tzinfo is not None

    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == weather.OPEN_METEO_FORECAST_URL
    assert call["timeout"] == weather.HTTP_TIMEOUT_SECONDS
    params = call["params"]
    assert params["latitude"] == pytest.approx(weather.AP_DISTRICTS["Krishna"][0])
    assert params["longitude"] == pytest.approx(weather.AP_DISTRICTS["Krishna"][1])
    assert params["current"] == "temperature_2m,relative_humidity_2m,precipitation"
    assert params["daily"] == (
        "temperature_2m_max,temperature_2m_min,precipitation_sum"
    )
    assert params["past_days"] == 30
    assert params["forecast_days"] == 16
    assert params["timezone"] == "Asia/Kolkata"


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("Vijayawada", "NTR"),
        ("Kadapa", "YSR Kadapa"),
        ("Nellore", "Sri Potti Sriramulu Nellore"),
        ("dr. b.r. ambedkar konaseema", "Dr. B.R. Ambedkar Konaseema"),
        ("Chittoor district", "Chittoor"),
        ("  SRIKAKULAM  ", "Srikakulam"),
    ],
)
def test_district_aliases(monkeypatch, alias, expected):
    install_fake_http(monkeypatch)

    response = weather.get_live_weather(district=alias)

    assert response.district == expected
    assert response.location == expected


def test_district_names_cover_all_26():
    names = weather.district_names()

    assert len(names) == 26
    assert names == sorted(names)
    assert "Krishna" in names
    assert "YSR Kadapa" in names


def test_every_district_headquarters_is_inside_ap():
    for name, (lat, lon) in weather.AP_DISTRICTS.items():
        assert weather.point_in_ap(lat, lon), name


def test_cache_returns_same_response_for_15_minutes(monkeypatch):
    calls = install_fake_http(monkeypatch)

    first = weather.get_live_weather(district="Krishna")
    second = weather.get_live_weather(district="Krishna")

    assert first is second
    assert len(calls) == 1


def test_cache_expires_after_ttl(monkeypatch):
    clock = {"now": 1_000.0}
    monkeypatch.setattr(weather, "_now", lambda: clock["now"])
    calls = install_fake_http(monkeypatch)

    weather.get_live_weather(district="Krishna")
    clock["now"] += weather.CACHE_TTL_SECONDS - 1
    weather.get_live_weather(district="Krishna")
    assert len(calls) == 1

    clock["now"] += 2
    weather.get_live_weather(district="Krishna")
    assert len(calls) == 2


def test_point_inside_ap(monkeypatch):
    calls = install_fake_http(monkeypatch)

    response = weather.get_live_weather(latitude=16.5062, longitude=80.6480)

    assert response.district is None
    assert response.location == "16.5062, 80.6480"
    assert calls[0]["params"]["latitude"] == pytest.approx(16.5062)
    assert calls[0]["params"]["longitude"] == pytest.approx(80.6480)


@pytest.mark.parametrize(
    ("lat", "lon"),
    [
        (17.3850, 78.4867),   # Hyderabad, Telangana
        (13.0827, 80.2707),   # Chennai, Tamil Nadu
        (28.6139, 77.2090),   # New Delhi
        (15.0, 70.0),         # Arabian Sea
    ],
)
def test_point_outside_ap_rejected(monkeypatch, lat, lon):
    calls = install_fake_http(monkeypatch)

    with pytest.raises(weather.OutsideAndhraPradeshError):
        weather.get_live_weather(latitude=lat, longitude=lon)

    assert calls == []


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (16.5062, 80.6480, True),    # Vijayawada
        (17.6868, 83.2185, True),    # Visakhapatnam
        (13.6288, 79.4192, True),    # Tirupati
        (14.6819, 77.6006, True),    # Anantapur
        (17.3850, 78.4867, False),   # Hyderabad
        (12.9716, 77.5946, False),   # Bengaluru
        (21.1458, 79.0882, False),   # Nagpur
    ],
)
def test_point_in_ap_polygon(lat, lon, expected):
    assert weather.point_in_ap(lat, lon) is expected


def test_endpoint_district(monkeypatch, client):
    install_fake_http(monkeypatch)

    response = client.get("/api/live-weather", params={"district": "Krishna"})

    assert response.status_code == 200
    body = response.json()
    assert body["location"] == "Krishna"
    assert body["district"] == "Krishna"
    assert body["source"] == "open-meteo"
    assert body["fetched_at"]
    assert body["current"] == {
        "time": "2026-11-09T23:15",
        "temperature_c": 28.4,
        "humidity_pct": 72.0,
        "precipitation_mm": 0.2,
    }
    assert body["daily"][1] == {
        "date": "2026-11-09",
        "temperature_max_c": 30.8,
        "temperature_min_c": 21.0,
        "precipitation_mm": 2.4,
    }


def test_endpoint_point(monkeypatch, client):
    install_fake_http(monkeypatch)

    response = client.get(
        "/api/live-weather", params={"lat": 16.5062, "lon": 80.6480}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["district"] is None
    assert body["location"] == "16.5062, 80.6480"


@pytest.mark.parametrize(
    ("params", "detail_part"),
    [
        ({}, "Provide district or both lat and lon"),
        ({"lat": 16.5}, "Provide both lat and lon"),
        ({"lon": 80.6}, "Provide both lat and lon"),
        ({"district": "Krishna", "lat": 16.5, "lon": 80.6}, "not both"),
    ],
)
def test_endpoint_bad_query_returns_400(client, params, detail_part):
    response = client.get("/api/live-weather", params=params)

    assert response.status_code == 400
    assert detail_part in response.json()["detail"]


def test_endpoint_unknown_district_returns_404(client):
    response = client.get("/api/live-weather", params={"district": "Nagpur"})

    assert response.status_code == 404
    assert "Unknown Andhra Pradesh district" in response.json()["detail"]


@pytest.mark.parametrize(
    ("lat", "lon"),
    [(17.3850, 78.4867), (28.6139, 77.2090)],
)
def test_endpoint_outside_ap_returns_400(client, lat, lon):
    response = client.get("/api/live-weather", params={"lat": lat, "lon": lon})

    assert response.status_code == 400
    assert "outside Andhra Pradesh" in response.json()["detail"]


def test_provider_network_error_returns_502(monkeypatch, client):
    def fake_get(*args, **kwargs):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(weather.httpx, "get", fake_get)

    response = client.get("/api/live-weather", params={"district": "Krishna"})

    assert response.status_code == 502
    assert "Live weather provider unavailable" in response.json()["detail"]


def test_provider_http_error_returns_502(monkeypatch, client):
    install_fake_http(monkeypatch, status_code=503)

    response = client.get("/api/live-weather", params={"district": "Krishna"})

    assert response.status_code == 502
    assert "Live weather provider unavailable" in response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"current": {}, "daily": {}},
        {
            "current": {"temperature_2m": 28.0},
            "daily": {
                "time": ["2026-11-09"],
                "temperature_2m_max": [31.0, 32.0],
                "temperature_2m_min": [21.0],
                "precipitation_sum": [0.0],
            },
        },
        {"error": True, "reason": "Invalid latitude"},
        [],
    ],
)
def test_provider_malformed_response_returns_502(monkeypatch, client, payload):
    install_fake_http(monkeypatch, payload=payload)

    response = client.get("/api/live-weather", params={"district": "Krishna"})

    assert response.status_code == 502
    assert "Live weather provider unavailable" in response.json()["detail"]
