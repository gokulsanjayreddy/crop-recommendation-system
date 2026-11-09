"""Live weather for Andhra Pradesh from Open-Meteo (forecast API, no key).

District coordinates are representative points derived from the current
26-district Andhra Pradesh boundary published by udit-001/india-maps-data
(DataMeet / Election Commission of India, CC BY 2.5 IN):
https://github.com/udit-001/india-maps-data

The API returns current conditions plus 30 days of history and 16 days of
forecast. Results are cached in memory for 15 minutes per location.
"""
from __future__ import annotations

import math
import re
import threading
import time
from datetime import datetime, timezone

import httpx

from backend.schemas import LiveWeatherCurrent, LiveWeatherDaily, LiveWeatherResponse

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "open-meteo"
TIMEZONE = "Asia/Kolkata"
CACHE_TTL_SECONDS = 15 * 60
HTTP_TIMEOUT_SECONDS = 20.0
PAST_DAYS = 30
FORECAST_DAYS = 16
CURRENT_FIELDS = "temperature_2m,relative_humidity_2m,precipitation"
DAILY_FIELDS = "temperature_2m_max,temperature_2m_min,precipitation_sum"


class WeatherProviderError(RuntimeError):
    """Open-Meteo could not be reached or returned unusable data."""


class WeatherQueryError(ValueError):
    """The request did not contain one valid district or point."""


class UnknownDistrictError(ValueError):
    """The district name is not one of Andhra Pradesh's 26 districts."""


class OutsideAndhraPradeshError(ValueError):
    """The supplied latitude/longitude falls outside Andhra Pradesh."""


# Weather is sampled at each district headquarters (the usual reference point
# for district-level weather). Coordinates were checked against Open-Meteo's
# geocoding results for India / Andhra Pradesh.
AP_DISTRICTS: dict[str, tuple[float, float]] = {
    "Alluri Sitharama Raju": (18.0778, 82.6604),   # Paderu
    "Anakapalli": (17.6913, 83.0039),              # Anakapalle
    "Anantapuramu": (14.6778, 77.6081),            # Anantapur
    "Annamayya": (14.0572, 78.7506),               # Rayachoti
    "Bapatla": (15.9042, 80.4674),                 # Bapatla
    "Chittoor": (13.2105, 79.0956),                # Chittoor
    "Dr. B.R. Ambedkar Konaseema": (16.5787, 82.0061),  # Amalapuram
    "East Godavari": (17.0052, 81.7778),           # Rajahmundry
    "Eluru": (16.7131, 81.1044),                   # Eluru
    "Guntur": (16.2997, 80.4573),                  # Guntur
    "Kakinada": (16.9604, 82.2381),                # Kakinada
    "Krishna": (16.1875, 81.1389),                 # Machilipatnam
    "Kurnool": (15.8289, 78.0360),                 # Kurnool
    "Nandyal": (15.4780, 78.4836),                 # Nandyal
    "NTR": (16.5074, 80.6466),                     # Vijayawada
    "Palnadu": (16.2349, 80.0493),                 # Narasaraopet
    "Parvathipuram Manyam": (18.7817, 83.4268),    # Parvathipuram
    "Prakasam": (15.5036, 80.0445),                # Ongole
    "Srikakulam": (18.2989, 83.8975),              # Srikakulam
    "Sri Potti Sriramulu Nellore": (14.4499, 79.9870),  # Nellore
    "Sri Sathya Sai": (14.1652, 77.8117),          # Puttaparthi
    "Tirupati": (13.6355, 79.4199),                # Tirupati
    "Visakhapatnam": (17.6801, 83.2016),           # Visakhapatnam
    "Vizianagaram": (18.1169, 83.4115),            # Vizianagaram
    "West Godavari": (16.5408, 81.5232),           # Bhimavaram
    "YSR Kadapa": (14.4800, 78.8235),              # Kadapa
}

# Extra spellings, headquarters and common short names. Keys are normalised
# before lookup, so case, punctuation and spacing do not matter.
_EXTRA_ALIASES = {
    "Alluri Sitarama Raju": "Alluri Sitharama Raju",
    "Alluri Seetharama Raju": "Alluri Sitharama Raju",
    "ASR": "Alluri Sitharama Raju",
    "Paderu": "Alluri Sitharama Raju",
    "Anakapalle": "Anakapalli",
    "Anantapur": "Anantapuramu",
    "Anantapuram": "Anantapuramu",
    "Ananthapuram": "Anantapuramu",
    "Ananthapuramu": "Anantapuramu",
    "Amalapuram": "Dr. B.R. Ambedkar Konaseema",
    "BR Ambedkar Konaseema": "Dr. B.R. Ambedkar Konaseema",
    "Konaseema": "Dr. B.R. Ambedkar Konaseema",
    "Rajahmundry": "East Godavari",
    "Rajamahendravaram": "East Godavari",
    "Bhimavaram": "West Godavari",
    "Cuddapah": "YSR Kadapa",
    "Kadapa": "YSR Kadapa",
    "YSR": "YSR Kadapa",
    "Nellore": "Sri Potti Sriramulu Nellore",
    "SPS Nellore": "Sri Potti Sriramulu Nellore",
    "SPSR Nellore": "Sri Potti Sriramulu Nellore",
    "Narasaraopet": "Palnadu",
    "Parvathipuram": "Parvathipuram Manyam",
    "Puttaparthi": "Sri Sathya Sai",
    "Rayachoti": "Annamayya",
    "Rayachoty": "Annamayya",
    "Vijayawada": "NTR",
    "Visakha": "Visakhapatnam",
    "Vizag": "Visakhapatnam",
}


def _normalise(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())


_DISTRICT_ALIASES = {_normalise(name): name for name in AP_DISTRICTS}
_DISTRICT_ALIASES.update(
    {_normalise(alias): name for alias, name in _EXTRA_ALIASES.items()}
)

# Simplified outer boundary of Andhra Pradesh, as (longitude, latitude).
# Derived from the same 26-district dataset with ~3 km simplification; used
# only to reject points that are not in Andhra Pradesh.
AP_BOUNDARY: tuple[tuple[float, float], ...] = (
    (78.2520, 12.8574), (78.3564, 12.9382), (78.4656, 12.8636), (78.4121, 12.9430),
    (78.5788, 13.1660), (78.5510, 13.1965), (78.5876, 13.2789), (78.3774, 13.3316),
    (78.4090, 13.3405), (78.3655, 13.3591), (78.4019, 13.5873), (78.1937, 13.5644),
    (78.1684, 13.6547), (78.0873, 13.6434), (78.1244, 13.8448), (78.0510, 13.8952),
    (77.9543, 13.8262), (77.9889, 13.9538), (77.9277, 13.9043), (77.8285, 13.9433),
    (77.8385, 13.8686), (77.7209, 13.7989), (77.7175, 13.7430), (77.6793, 13.7858),
    (77.6267, 13.7345), (77.5309, 13.7554), (77.5249, 13.6913), (77.4554, 13.6827),
    (77.4322, 13.8416), (77.2583, 13.8461), (77.2451, 13.9033), (77.2002, 13.8632),
    (77.1847, 13.9241), (77.1283, 13.8566), (77.1730, 13.7627), (77.0762, 13.7427),
    (77.0244, 13.7792), (77.0000, 13.7448), (76.9781, 13.8273), (77.0408, 13.9347),
    (76.9332, 14.0301), (76.9788, 14.0700), (76.8964, 14.1685), (77.0233, 14.1760),
    (77.0302, 14.0571), (77.1310, 14.0445), (77.1404, 14.0037), (77.3212, 14.0301),
    (77.3705, 13.9528), (77.3475, 13.9160), (77.3993, 13.8885), (77.4375, 13.9739),
    (77.3326, 14.0304), (77.4014, 14.1202), (77.3514, 14.1312), (77.5162, 14.1858),
    (77.4969, 14.2798), (77.4070, 14.3384), (77.3915, 14.1995), (77.3620, 14.2773),
    (77.2824, 14.2840), (77.2870, 14.3395), (77.1397, 14.3409), (77.1017, 14.2175),
    (76.9417, 14.2443), (76.9556, 14.2929), (76.8848, 14.3848), (76.9421, 14.4002),
    (76.9757, 14.4851), (76.8659, 14.4745), (76.7642, 14.6030), (76.7837, 14.7845),
    (76.8535, 14.8090), (76.8703, 14.9358), (76.8666, 14.9708), (76.7660, 14.9750),
    (76.7775, 15.0783), (77.0826, 15.0065), (77.1687, 15.1746), (77.1250, 15.2273),
    (77.1683, 15.2652), (77.1139, 15.3334), (77.0624, 15.3280), (76.9747, 15.4945),
    (77.0270, 15.5037), (77.0351, 15.6382), (77.1221, 15.6292), (77.1305, 15.6636),
    (77.0489, 15.7389), (77.0655, 15.8277), (77.0282, 15.8360), (77.0669, 15.9035),
    (77.2479, 15.9638), (77.8040, 15.8755), (77.8895, 15.9067), (78.0087, 15.8631),
    (78.0339, 15.9070), (78.1336, 15.8369), (78.2515, 15.9360), (78.2603, 16.0253),
    (78.4061, 16.0758), (78.5507, 16.0427), (78.6278, 16.0878), (78.7840, 16.0215),
    (78.8401, 16.0790), (78.8344, 16.1458), (78.8956, 16.0860), (78.9060, 16.1842),
    (79.0111, 16.2417), (79.2194, 16.2317), (79.2147, 16.4878), (79.2587, 16.5672),
    (79.4175, 16.5800), (79.7761, 16.7315), (79.8783, 16.6970), (79.9085, 16.6348),
    (79.9628, 16.6431), (80.0694, 16.7965), (80.0166, 16.9147), (80.1961, 17.0448),
    (80.2941, 16.9968), (80.3827, 16.8163), (80.3826, 16.8652), (80.5722, 16.7676),
    (80.6132, 16.7958), (80.5647, 16.8367), (80.5812, 16.9368), (80.3630, 16.9757),
    (80.4106, 17.0926), (80.4647, 17.0304), (80.5798, 17.1532), (80.6699, 17.1017),
    (80.6549, 17.0686), (80.8454, 17.0398), (80.9189, 17.2200), (81.0304, 17.1904),
    (81.1707, 17.2314), (81.1895, 17.3236), (81.2751, 17.3177), (81.3219, 17.3739),
    (81.1491, 17.4632), (81.1294, 17.5252), (81.0169, 17.5197), (80.9674, 17.5988),
    (80.8556, 17.6030), (80.9109, 17.6545), (80.9000, 17.7521), (80.9737, 17.7794),
    (81.0730, 17.6968), (81.0889, 17.8108), (81.1594, 17.8527), (81.3945, 17.7949),
    (81.4726, 17.8362), (81.6183, 17.8232), (82.0326, 18.0688), (82.2674, 17.9959),
    (82.3724, 18.1471), (82.3115, 18.2043), (82.3927, 18.2979), (82.3394, 18.3259),
    (82.3856, 18.3674), (82.3657, 18.4222), (82.4821, 18.5484), (82.5618, 18.4477),
    (82.5411, 18.4008), (82.6209, 18.3599), (82.5821, 18.3151), (82.6374, 18.2367),
    (82.6423, 18.3017), (82.7751, 18.3401), (82.8038, 18.4495), (82.8972, 18.4226),
    (82.9132, 18.3686), (83.0545, 18.3798), (83.0670, 18.4299), (83.0211, 18.4559),
    (83.0952, 18.5461), (83.0430, 18.5474), (83.0103, 18.6465), (83.1367, 18.7861),
    (83.2106, 18.7325), (83.2224, 18.7763), (83.4042, 18.8389), (83.3689, 18.9613),
    (83.3369, 18.9249), (83.3131, 18.9975), (83.4008, 19.0094), (83.4614, 18.9547),
    (83.4686, 19.0936), (83.5358, 19.0117), (83.6259, 19.1627), (83.7544, 18.9250),
    (83.7878, 18.9162), (83.7472, 18.9867), (83.7954, 19.0181), (83.8779, 18.8272),
    (84.0347, 18.8111), (84.0894, 18.7537), (84.3200, 18.7884), (84.3434, 18.8758),
    (84.4367, 18.9228), (84.4211, 19.0222), (84.4762, 18.9896), (84.5820, 19.0739),
    (84.6004, 19.0246), (84.6688, 19.0757), (84.5958, 19.1318), (84.7126, 19.1579),
    (84.7539, 19.0613), (84.1246, 18.3118), (83.5704, 18.0114), (83.3455, 17.7259),
    (83.3062, 17.6882), (83.2638, 17.7121), (83.2953, 17.6764), (83.2314, 17.6275),
    (83.2131, 17.5911), (82.5825, 17.2744), (82.3178, 17.0579), (82.2450, 16.9402),
    (82.2708, 16.8771), (82.3556, 16.8516), (82.3670, 16.7293), (82.3017, 16.5729),
    (81.7227, 16.3103), (81.4768, 16.3526), (81.3022, 16.3025), (81.2087, 16.1871),
    (81.1398, 15.9755), (81.0031, 15.8338), (81.0172, 15.7685), (80.9396, 15.7213),
    (80.8246, 15.7146), (80.7958, 15.7444), (80.7724, 15.8008), (80.8160, 15.7418),
    (80.8093, 15.8375), (80.6959, 15.8808), (80.4632, 15.8204), (80.2856, 15.6895),
    (80.1100, 15.3442), (80.0480, 15.0821), (80.0988, 14.7773), (80.1941, 14.5883),
    (80.1271, 14.1582), (80.2526, 13.7800), (80.2426, 13.4707), (79.9994, 13.5421),
    (80.0457, 13.4925), (79.9720, 13.4685), (79.9419, 13.3598), (79.7339, 13.2849),
    (79.7976, 13.2364), (79.7612, 13.2058), (79.7051, 13.2202), (79.6823, 13.2946),
    (79.5773, 13.2577), (79.5299, 13.3416), (79.4390, 13.3477), (79.3839, 13.3081),
    (79.4480, 13.2984), (79.4120, 13.2635), (79.4556, 13.2348), (79.4399, 13.1859),
    (79.3769, 13.1881), (79.3657, 13.1275), (79.3068, 13.1045), (79.2355, 13.1685),
    (79.1650, 13.0191), (78.9915, 13.0878), (78.9262, 13.0790), (78.9389, 13.0311),
    (78.8937, 13.0310), (78.8877, 13.0972), (78.7161, 13.0679), (78.7053, 13.0152),
    (78.6222, 12.9885), (78.6583, 12.9298), (78.5570, 12.6978), (78.4903, 12.7397),
    (78.5208, 12.7130), (78.4665, 12.6227), (78.2001, 12.6926), (78.2520, 12.8574),
)


def district_names() -> list[str]:
    """All canonical Andhra Pradesh district names, sorted for the UI."""
    return sorted(AP_DISTRICTS)


def resolve_district(name: str) -> tuple[str, float, float]:
    """Return (canonical name, latitude, longitude) for a district."""
    key = _normalise(name)
    if key.endswith(" district"):
        key = key[: -len(" district")].strip()
    canonical = _DISTRICT_ALIASES.get(key)
    if canonical is None:
        raise UnknownDistrictError(f"Unknown Andhra Pradesh district: {name}")
    lat, lon = AP_DISTRICTS[canonical]
    return canonical, lat, lon


def point_in_ap(latitude: float, longitude: float) -> bool:
    """Ray-casting point-in-polygon test against the Andhra Pradesh outline."""
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return False
    x, y = longitude, latitude
    inside = False
    j = len(AP_BOUNDARY) - 1
    for i, (xi, yi) in enumerate(AP_BOUNDARY):
        xj, yj = AP_BOUNDARY[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------- HTTP + cache
_cache: dict[str, tuple[float, LiveWeatherResponse]] = {}
_cache_lock = threading.Lock()


def _now() -> float:
    return time.monotonic()


def clear_cache() -> None:
    """Drop all cached responses (used by tests and manual refreshes)."""
    with _cache_lock:
        _cache.clear()


def _cache_get(key: str) -> LiveWeatherResponse | None:
    now = _now()
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, response = entry
        if expires_at <= now:
            _cache.pop(key, None)
            return None
        return response


def _cache_set(key: str, response: LiveWeatherResponse) -> None:
    with _cache_lock:
        _cache[key] = (_now() + CACHE_TTL_SECONDS, response)


def _fetch(latitude: float, longitude: float) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": CURRENT_FIELDS,
        "daily": DAILY_FIELDS,
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "timezone": TIMEZONE,
    }
    try:
        response = httpx.get(
            OPEN_METEO_FORECAST_URL, params=params, timeout=HTTP_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise WeatherProviderError(f"Open-Meteo request failed: {exc}") from exc
    except ValueError as exc:
        raise WeatherProviderError("Open-Meteo returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise WeatherProviderError("Open-Meteo returned an unexpected response")
    if payload.get("error"):
        reason = payload.get("reason") or "unknown provider error"
        raise WeatherProviderError(f"Open-Meteo error: {reason}")
    return payload


def _as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse(
    payload: dict,
    *,
    location: str,
    district: str | None,
    latitude: float,
    longitude: float,
) -> LiveWeatherResponse:
    try:
        current_raw = payload["current"]
        daily_raw = payload["daily"]
        dates = daily_raw["time"]
        tmax = daily_raw["temperature_2m_max"]
        tmin = daily_raw["temperature_2m_min"]
        rain = daily_raw["precipitation_sum"]
        if not all(isinstance(seq, list) for seq in (dates, tmax, tmin, rain)):
            raise TypeError("daily fields are not lists")
    except (KeyError, TypeError) as exc:
        raise WeatherProviderError(
            "Open-Meteo response is missing current or daily fields"
        ) from exc

    if not (len(dates) == len(tmax) == len(tmin) == len(rain)):
        raise WeatherProviderError("Open-Meteo daily arrays have different lengths")

    daily = [
        LiveWeatherDaily(
            date=str(dates[i]),
            temperature_max_c=_as_float(tmax[i]),
            temperature_min_c=_as_float(tmin[i]),
            precipitation_mm=_as_float(rain[i]),
        )
        for i in range(len(dates))
    ]
    current = LiveWeatherCurrent(
        time=str(current_raw.get("time") or ""),
        temperature_c=_as_float(current_raw.get("temperature_2m")),
        humidity_pct=_as_float(current_raw.get("relative_humidity_2m")),
        precipitation_mm=_as_float(current_raw.get("precipitation")),
    )

    provider_lat = _as_float(payload.get("latitude"))
    provider_lon = _as_float(payload.get("longitude"))
    return LiveWeatherResponse(
        location=location,
        district=district,
        latitude=provider_lat if provider_lat is not None else latitude,
        longitude=provider_lon if provider_lon is not None else longitude,
        timezone=str(payload.get("timezone") or TIMEZONE),
        current=current,
        daily=daily,
        source=SOURCE,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def get_live_weather(
    district: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> LiveWeatherResponse:
    """Fetch current + 30 past + 16 forecast days for a district or point."""
    district = district.strip() if district else None
    has_point = latitude is not None or longitude is not None

    if district and has_point:
        raise WeatherQueryError("Use either district or lat/lon, not both")
    if not district and not has_point:
        raise WeatherQueryError("Provide district or both lat and lon")
    if has_point and (latitude is None or longitude is None):
        raise WeatherQueryError("Provide both lat and lon")

    if district:
        canonical, lat, lon = resolve_district(district)
        location = canonical
        cache_key = f"district:{canonical}"
    else:
        assert latitude is not None and longitude is not None
        if not point_in_ap(latitude, longitude):
            raise OutsideAndhraPradeshError(
                "The supplied latitude/longitude is outside Andhra Pradesh"
            )
        canonical = None
        lat, lon = latitude, longitude
        location = f"{latitude:.4f}, {longitude:.4f}"
        cache_key = f"point:{latitude:.3f},{longitude:.3f}"

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    payload = _fetch(lat, lon)
    response = _parse(
        payload,
        location=location,
        district=canonical,
        latitude=lat,
        longitude=lon,
    )
    _cache_set(cache_key, response)
    return response
