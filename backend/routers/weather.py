"""GET /api/live-weather - live conditions for an AP district or point."""
from fastapi import APIRouter, HTTPException, Query

from backend.schemas import LiveWeatherResponse
from backend.services.weather import (
    OutsideAndhraPradeshError,
    UnknownDistrictError,
    WeatherProviderError,
    WeatherQueryError,
    get_live_weather,
)

router = APIRouter()


@router.get("/api/live-weather", response_model=LiveWeatherResponse)
def live_weather(
    district: str | None = Query(
        None, description="Andhra Pradesh district name, e.g. Krishna"
    ),
    lat: float | None = Query(
        None, ge=-90, le=90, description="Latitude (use together with lon)"
    ),
    lon: float | None = Query(
        None, ge=-180, le=180, description="Longitude (use together with lat)"
    ),
):
    """Current conditions plus 30 past and 16 forecast days from Open-Meteo."""
    try:
        return get_live_weather(district=district, latitude=lat, longitude=lon)
    except UnknownDistrictError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (OutsideAndhraPradeshError, WeatherQueryError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WeatherProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Live weather provider unavailable: {exc}",
        ) from exc
