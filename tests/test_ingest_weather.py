"""Tests for python -m backend.ingest weather pipeline with mocked Open-Meteo archive API.

All HTTP is mocked via httpx.MockTransport; no test touches the live provider.
The API variable names were verified separately against a live archive response
(temperature_2m_max, temperature_2m_min, precipitation_sum,
relative_humidity_2m_mean, et0_fao_evapotranspiration,
soil_moisture_0_to_100cm_mean) and are used verbatim below.
"""
from datetime import date, timedelta

import httpx
import pytest

from backend.ingest import ingest_weather
from backend.db import WeatherDaily, ReferencePoint, init_db, SessionLocal, engine


def make_mock_payload(dates, tmax, tmin, rain, humidity, et0=None, soil=None):
    """Build a minimal archive API payload keyed by the verified variable names."""
    daily = {
        "time": dates,
        "temperature_2m_max": tmax,
        "temperature_2m_min": tmin,
        "precipitation_sum": rain,
        "relative_humidity_2m_mean": humidity,
    }
    if et0 is not None:
        daily["et0_fao_evapotranspiration"] = et0
    if soil is not None:
        daily["soil_moisture_0_to_100cm_mean"] = soil
    return {
        "latitude": 16.5,
        "longitude": 80.5,
        "timezone": "Asia/Kolkata",
        "daily": daily,
    }


@pytest.fixture(autouse=True)
def fresh_db():
    """Start with a fresh SQLite database for each test."""
    from backend.db import Base
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def ref_points():
    """Populate reference_points with three AP districts."""
    db = SessionLocal()
    try:
        for name, (lat, lon) in {
            "Krishna": (16.1875, 81.1389),
            "Guntur": (16.2997, 80.4573),
            "Visakhapatnam": (17.6801, 83.2016),
        }.items():
            db.add(ReferencePoint(district=name, lat=lat, lon=lon, source="open-meteo"))
        db.commit()
    finally:
        db.close()


def build_mock_client(payload):
    """httpx.Client backed by a MockTransport returning payload for archive URLs."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"url": str(request.url), "params": dict(request.url.params)})
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return client, calls


@pytest.mark.usefixtures("fresh_db", "ref_points")
def test_ingest_weather_basic_creates_rows(ref_points):
    """Basic ingestion: one row per district per returned date, using verified names."""
    from backend.db import WeatherDaily, SessionLocal

    five_dates = [date(2010, 1, 1) + timedelta(days=i) for i in range(5)]
    payload = make_mock_payload(
        dates=[d.isoformat() for d in five_dates],
        tmax=[30.0, 31.0, 29.5, 32.0, 30.5],
        tmin=[21.0, 21.5, 20.8, 22.0, 21.3],
        rain=[0.0, 2.4, 0.0, 5.6, 1.1],
        humidity=[65.0, 68.0, 62.0, 70.0, 66.0],
        et0=[5.2, 4.8, 5.0, 5.5, 4.9],
        soil=[0.35, 0.33, 0.34, 0.36, 0.32],
    )
    client, calls = build_mock_client(payload)

    with SessionLocal() as db:
        init_db(db.get_bind())
        ingest_weather(db=db, client=client, verbose=False)

    with SessionLocal() as db:
        count = db.query(WeatherDaily).count()
    assert count == 15  # 3 districts x 5 days

    # One extended request per district; variable names verified live.
    assert len(calls) == 3
    daily_param = calls[0]["params"]["daily"]
    assert "relative_humidity_2m_mean" in daily_param
    assert "et0_fao_evapotranspiration" in daily_param
    assert "soil_moisture_0_to_100cm_mean" in daily_param


@pytest.mark.usefixtures("fresh_db", "ref_points")
def test_ingest_weather_idempotent_no_duplicates(ref_points):
    """Re-running ingest_weather adds no duplicate rows."""
    from backend.db import WeatherDaily, SessionLocal

    five_dates = [date(2010, 1, 1) + timedelta(days=i) for i in range(5)]
    payload = make_mock_payload(
        dates=[d.isoformat() for d in five_dates],
        tmax=[30.0, 31.0, 29.5, 32.0, 30.5],
        tmin=[21.0, 21.5, 20.8, 22.0, 21.3],
        rain=[0.0, 2.4, 0.0, 5.6, 1.1],
        humidity=[65.0, 68.0, 62.0, 70.0, 66.0],
    )

    with SessionLocal() as db:
        ingest_weather(db=db, client=build_mock_client(payload)[0], verbose=False)
        count1 = db.query(WeatherDaily).count()
        # Second run, same payload -> no new rows
        ingest_weather(db=db, client=build_mock_client(payload)[0], verbose=False)
        count2 = db.query(WeatherDaily).count()
    assert count2 == count1 == 15


@pytest.mark.usefixtures("fresh_db", "ref_points")
def test_ingest_weather_stores_humidity_et0_soil(ref_points):
    """relative_humidity, ET0 and soil moisture values are persisted."""
    from backend.db import WeatherDaily, SessionLocal

    five_dates = [date(2010, 1, 1) + timedelta(days=i) for i in range(5)]
    payload = make_mock_payload(
        dates=[d.isoformat() for d in five_dates],
        tmax=[30.0, 31.0, 29.5, 32.0, 30.5],
        tmin=[21.0, 21.5, 20.8, 22.0, 21.3],
        rain=[0.0, 2.4, 0.0, 5.6, 1.1],
        humidity=[65.0, 68.0, 62.0, 70.0, 66.0],
        et0=[5.2, 4.8, 5.0, 5.5, 4.9],
        soil=[0.35, 0.33, 0.34, 0.36, 0.32],
    )

    with SessionLocal() as db:
        ingest_weather(db=db, client=build_mock_client(payload)[0], verbose=False)
        row = (
            db.query(WeatherDaily)
            .filter(WeatherDaily.point == "Krishna")
            .filter(WeatherDaily.date == five_dates[0])
            .one()
        )
        assert row.humidity == 65.0
        assert row.et0 == 5.2
        assert row.soil_moisture == 0.35
        assert row.tmean == round((30.0 + 21.0) / 2, 2)
        assert row.source == "open-meteo"


@pytest.mark.usefixtures("fresh_db", "ref_points")
def test_ingest_weather_never_overwrites_reanalysis(ref_points):
    """Existing reanalysis rows are kept, not overwritten by a later fetch."""
    from backend.db import WeatherDaily, SessionLocal

    five_dates = [date(2010, 1, 1) + timedelta(days=i) for i in range(5)]
    payload = make_mock_payload(
        dates=[d.isoformat() for d in five_dates],
        tmax=[30.0, 31.0, 29.5, 32.0, 30.5],
        tmin=[21.0, 21.5, 20.8, 22.0, 21.3],
        rain=[0.0, 2.4, 0.0, 5.6, 1.1],
        humidity=[65.0, 68.0, 62.0, 70.0, 66.0],
    )

    with SessionLocal() as db:
        # A pre-existing reanalysis row with a distinctive value.
        db.add(
            WeatherDaily(
                point="Krishna", date=five_dates[0],
                tmax=99.0, tmin=99.0, tmean=99.0, rain_mm=99.0,
                humidity=99.0, source="open-meteo",
            )
        )
        db.commit()
        ingest_weather(db=db, client=build_mock_client(payload)[0], verbose=False)
        row = (
            db.query(WeatherDaily)
            .filter(WeatherDaily.point == "Krishna")
            .filter(WeatherDaily.date == five_dates[0])
            .one()
        )
        assert row.tmax == 99.0  # untouched
        count = db.query(WeatherDaily).filter(WeatherDaily.point == "Krishna").count()
    assert count == 5


@pytest.mark.usefixtures("fresh_db", "ref_points")
def test_ingest_weather_reports_gaps(ref_points, capsys):
    """With only 5 of ~6100 expected days, gap listing is printed."""
    from backend.db import SessionLocal

    five_dates = [date(2010, 1, 1) + timedelta(days=i) for i in range(5)]
    payload = make_mock_payload(
        dates=[d.isoformat() for d in five_dates],
        tmax=[30.0] * 5, tmin=[21.0] * 5,
        rain=[0.0] * 5, humidity=[65.0] * 5,
    )
    with SessionLocal() as db:
        stats = ingest_weather(db=db, client=build_mock_client(payload)[0], verbose=False)
    captured = capsys.readouterr()
    assert "Coverage gaps" in captured.out
    assert "missing dates" in captured.out
    assert any(s["cov_pct"] < 95 for s in stats.values())


@pytest.mark.usefixtures("fresh_db")
def test_ingest_weather_no_reference_points(capsys):
    """With no reference points, ingestion reports and returns empty."""
    from backend.db import SessionLocal

    with SessionLocal() as db:
        result = ingest_weather(db=db, client=build_mock_client({})[0], verbose=False)
    assert result == {}
    assert "No reference points" in capsys.readouterr().out
