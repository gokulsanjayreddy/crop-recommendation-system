"""CLI and ingestion pipeline for Andhra Pradesh spatial and reference data."""
import sys
import time
import argparse
from datetime import date, timedelta
from typing import Optional, List, Tuple, Dict, Any
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db import SessionLocal, ReferencePoint, WeatherDaily, init_db

# 26 districts of Andhra Pradesh after the April 2022 reorganization with their headquarters
AP_DISTRICTS: List[Dict[str, Any]] = [
    {
        "district": "Alluri Sitharama Raju",
        "headquarters": "Paderu",
        "aliases": ["Paderu", "Alluri Sitharama Raju"],
    },
    {
        "district": "Anakapalli",
        "headquarters": "Anakapalli",
        "aliases": ["Anakapalle", "Anakapalli"],
    },
    {
        "district": "Ananthapuramu",
        "headquarters": "Anantapur",
        "aliases": ["Anantapur", "Ananthapuramu"],
    },
    {
        "district": "Annamayya",
        "headquarters": "Rayachoti",
        "aliases": ["Rayachoti", "Annamayya"],
    },
    {
        "district": "Bapatla",
        "headquarters": "Bapatla",
        "aliases": ["Bapatla"],
    },
    {
        "district": "Chittoor",
        "headquarters": "Chittoor",
        "aliases": ["Chittoor"],
    },
    {
        "district": "Dr. B.R. Ambedkar Konaseema",
        "headquarters": "Amalapuram",
        "aliases": ["Amalapuram", "Konaseema", "Dr. B.R. Ambedkar Konaseema"],
    },
    {
        "district": "East Godavari",
        "headquarters": "Rajamahendravaram",
        "aliases": ["Rajamahendravaram", "Rajahmundry", "East Godavari"],
    },
    {
        "district": "Eluru",
        "headquarters": "Eluru",
        "aliases": ["Eluru"],
    },
    {
        "district": "Guntur",
        "headquarters": "Guntur",
        "aliases": ["Guntur"],
    },
    {
        "district": "Kakinada",
        "headquarters": "Kakinada",
        "aliases": ["Kakinada"],
    },
    {
        "district": "Krishna",
        "headquarters": "Machilipatnam",
        "aliases": ["Machilipatnam", "Krishna"],
    },
    {
        "district": "Kurnool",
        "headquarters": "Kurnool",
        "aliases": ["Kurnool"],
    },
    {
        "district": "Nandyal",
        "headquarters": "Nandyal",
        "aliases": ["Nandyal"],
    },
    {
        "district": "NTR",
        "headquarters": "Vijayawada",
        "aliases": ["Vijayawada", "NTR"],
    },
    {
        "district": "Palnadu",
        "headquarters": "Narasaraopet",
        "aliases": ["Narasaraopet", "Palnadu"],
    },
    {
        "district": "Parvathipuram Manyam",
        "headquarters": "Parvatipuram",
        "aliases": ["Parvatipuram", "Parvathipuram", "Parvathipuram Manyam"],
    },
    {
        "district": "Prakasam",
        "headquarters": "Ongole",
        "aliases": ["Ongole", "Prakasam"],
    },
    {
        "district": "Sri Potti Sriramulu Nellore",
        "headquarters": "Nellore",
        "aliases": ["Nellore", "Sri Potti Sriramulu Nellore"],
    },
    {
        "district": "Sri Sathya Sai",
        "headquarters": "Puttaparthi",
        "aliases": ["Puttaparthi", "Sri Sathya Sai"],
    },
    {
        "district": "Srikakulam",
        "headquarters": "Srikakulam",
        "aliases": ["Srikakulam"],
    },
    {
        "district": "Tirupati",
        "headquarters": "Tirupati",
        "aliases": ["Tirupati"],
    },
    {
        "district": "Visakhapatnam",
        "headquarters": "Visakhapatnam",
        "aliases": ["Visakhapatnam"],
    },
    {
        "district": "Vizianagaram",
        "headquarters": "Vizianagaram",
        "aliases": ["Vizianagaram"],
    },
    {
        "district": "West Godavari",
        "headquarters": "Bhimavaram",
        "aliases": ["Bhimavaram", "West Godavari"],
    },
    {
        "district": "YSR Kadapa",
        "headquarters": "Kadapa",
        "aliases": ["Kadapa", "Cuddapah", "YSR Kadapa"],
    },
]

OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def resolve_district_coordinates(
    district_info: Dict[str, Any],
    client: Optional[httpx.Client] = None,
) -> Optional[Tuple[float, float, str]]:
    """
    Resolve coordinates for a district via Open-Meteo Geocoding API.
    Returns (latitude, longitude, source) or None if resolution fails.
    """
    timeout = getattr(settings, "OPEN_METEO_TIMEOUT", 10.0)
    close_client = False
    if client is None:
        client = httpx.Client(timeout=timeout)
        close_client = True

    try:
        queries = district_info.get("aliases", [district_info["headquarters"]])
        for query in queries:
            params = {
                "name": query,
                "count": 10,
                "language": "en",
                "format": "json",
            }
            try:
                response = client.get(OPEN_METEO_GEOCODING_URL, params=params)
                if response.status_code != 200:
                    continue
                data = response.json().get("results", [])
                # Filter for matches in India and preferably Andhra Pradesh
                ap_matches = [
                    r
                    for r in data
                    if r.get("country_code") == "IN"
                    and (
                        r.get("admin1") == "Andhra Pradesh"
                        or "Andhra Pradesh" in (r.get("admin1") or "")
                    )
                ]
                if ap_matches:
                    match = ap_matches[0]
                    return float(match["latitude"]), float(match["longitude"]), "open-meteo"

                # Fallback to general Indian match if no explicit AP admin1 label
                in_matches = [r for r in data if r.get("country_code") == "IN"]
                if in_matches:
                    match = in_matches[0]
                    return float(match["latitude"]), float(match["longitude"]), "open-meteo"
            except Exception:
                pass
            time.sleep(0.05)
        return None
    finally:
        if close_client:
            client.close()


def ingest_points(
    db: Optional[Session] = None,
    client: Optional[httpx.Client] = None,
    verbose: bool = True,
) -> Tuple[List[ReferencePoint], List[str]]:
    """
    Ingest reference coordinates for all 26 Andhra Pradesh districts.
    Saves to the reference_points table and returns (saved_records, failed_districts).
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Ensure reference_points table exists
        init_db(target_engine=db.get_bind())

        saved_records: List[ReferencePoint] = []
        failed_districts: List[str] = []

        if verbose:
            print(f"Resolving coordinates for {len(AP_DISTRICTS)} Andhra Pradesh districts...")

        for item in AP_DISTRICTS:
            district_name = item["district"]
            hq_name = item["headquarters"]
            coords = resolve_district_coordinates(item, client=client)

            if coords:
                lat, lon, source = coords
                # Check if district already exists in DB (idempotent upsert)
                existing = (
                    db.query(ReferencePoint)
                    .filter(ReferencePoint.district == district_name)
                    .first()
                )
                if existing:
                    existing.lat = lat
                    existing.lon = lon
                    existing.source = source
                    ref_point = existing
                else:
                    ref_point = ReferencePoint(
                        district=district_name,
                        lat=lat,
                        lon=lon,
                        source=source,
                    )
                    db.add(ref_point)
                db.commit()
                db.refresh(ref_point)
                saved_records.append(ref_point)
                if verbose:
                    print(
                        f"  [OK] {district_name:<28} (HQ: {hq_name:<18}) -> lat={lat:.4f}, lon={lon:.4f}"
                    )
            else:
                failed_districts.append(district_name)
                if verbose:
                    print(f"  [FAILED] Could not resolve coordinates for {district_name}")

        return saved_records, failed_districts
    finally:
        if close_db:
            db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Crop Recommendation System - Public Data Ingestion CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    points_parser = subparsers.add_parser(
        "points",
        help="Build Andhra Pradesh district reference points via Open-Meteo Geocoding API",
    )

    weather_parser = subparsers.add_parser(
        "weather",
        help="Ingest historical weather data from Open-Meteo archive (ERA5) for all AP districts",
    )

    args = parser.parse_args()

    if args.command == "points":
        saved, failed = ingest_points(verbose=True)
        print("\n" + "=" * 60)
        print(f"Ingestion summary: {len(saved)}/{len(AP_DISTRICTS)} districts populated.")
        if failed:
            print(f"WARNING: The following {len(failed)} district(s) failed to resolve:")
            for f in failed:
                print(f"  - {f}")
            sys.exit(1)
        else:
            print("SUCCESS: All Andhra Pradesh district reference points resolved and saved.")
            sys.exit(0)

    if args.command == "weather":
        ingest_weather(verbose=True)


def ingest_weather(db: Optional[Session] = None, client: Optional[httpx.Client] = None, verbose: bool = True) -> Dict[str, Any]:
    """Ingest historical weather data from Open-Meteo archive (ERA5) for all AP districts.

    Pulls data from 2010-01-01 to today-6 days for every reference point.
    Requests relative_humidity_2m_mean plus et0_fao_evapotranspiration and
    soil_moisture_0_to_100cm_mean (names verified against live Open-Meteo
    archive responses on 2026-11-16). If the optional variables are unavailable
    for a location, the request is retried with only the core variables.
    Upserts idempotently — never overwrites existing reanalysis rows with
    forecast rows. Returns a per-district coverage report.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    close_client = False
    if client is None:
        client = httpx.Client(timeout=settings.OPEN_METEO_TIMEOUT)
        close_client = True

    try:
        init_db(target_engine=db.get_bind())

        # Build district lat/lon from reference_points
        ref_result = db.execute(
            select(ReferencePoint.district, ReferencePoint.lat, ReferencePoint.lon)
        )
        reference_points = {
            row.district: {"lat": row.lat, "lon": row.lon}
            for row in ref_result.fetchall()
        }

        if not reference_points:
            print("No reference points found. Run `python -m backend.ingest points` first.")
            return {}

        today = date.today()
        end_date = today - timedelta(days=6)
        start_date = date(2010, 1, 1)
        expected_days = (end_date - start_date).days + 1

        OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

        # Variable names verified from a live archive response on 2026-11-16:
        CORE_VARS = "temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_mean"
        EXTENDED_VARS = CORE_VARS + ",et0_fao_evapotranspiration,soil_moisture_0_to_100cm_mean"

        district_stats: Dict[str, Dict[str, Any]] = {}

        for district, coords in reference_points.items():
            lat, lon = coords["lat"], coords["lon"]
            base_params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "timezone": "Asia/Kolkata",
            }

            # Try extended variables first; fall back to core if unsupported.
            payload = None
            last_error = None
            for var_set in (EXTENDED_VARS, CORE_VARS):
                params = dict(base_params)
                params["daily"] = var_set
                try:
                    response = client.get(
                        OPEN_METEO_ARCHIVE_URL, params=params, timeout=settings.OPEN_METEO_TIMEOUT
                    )
                    response.raise_for_status()
                    candidate = response.json()
                    if candidate.get("error"):
                        last_error = candidate.get("reason") or "provider error"
                        continue
                    payload = candidate
                    break
                except Exception as exc:
                    last_error = str(exc)
                    continue

            if payload is None:
                if verbose:
                    print(f"  [FAILED] {district}: request failed - {last_error}")
                district_stats[district] = {
                    "records": 0, "days_possible": expected_days,
                    "covered_days": 0, "error": last_error,
                    "missing_dates": [],
                }
                continue

            daily = payload.get("daily", {})
            dates = daily.get("time", [])
            tmax = daily.get("temperature_2m_max", [])
            tmin = daily.get("temperature_2m_min", [])
            rain = daily.get("precipitation_sum", [])
            humidity = daily.get("relative_humidity_2m_mean", [])
            et0 = daily.get("et0_fao_evapotranspiration", [])
            soil_moisture = daily.get("soil_moisture_0_to_100cm_mean", [])

            # Idempotent upsert: skip dates that already exist (never overwrite
            # reanalysis rows with forecast rows).
            existing_result = db.execute(
                select(WeatherDaily.date).where(WeatherDaily.point == district)
            )
            existing_dates = {row[0] for row in existing_result.fetchall()}

            new_rows: List[WeatherDaily] = []
            covered_dates: List[date] = []
            for i, date_str in enumerate(dates):
                try:
                    record_date = date.fromisoformat(date_str)
                except (ValueError, TypeError):
                    continue

                if record_date in existing_dates:
                    covered_dates.append(record_date)
                    continue

                if i >= len(tmax) or i >= len(tmin) or tmax[i] is None or tmin[i] is None:
                    continue

                tmax_val = float(tmax[i])
                tmin_val = float(tmin[i])
                tmean_val = round((tmax_val + tmin_val) / 2, 2)
                rain_val = float(rain[i]) if i < len(rain) and rain[i] is not None else None
                humidity_val = (
                    float(humidity[i]) if i < len(humidity) and humidity[i] is not None else None
                )
                et0_val = float(et0[i]) if i < len(et0) and et0[i] is not None else None
                soil_val = (
                    float(soil_moisture[i])
                    if i < len(soil_moisture) and soil_moisture[i] is not None else None
                )

                new_rows.append(
                    WeatherDaily(
                        point=district,
                        date=record_date,
                        tmax=tmax_val,
                        tmin=tmin_val,
                        tmean=tmean_val,
                        rain_mm=rain_val,
                        humidity=humidity_val,
                        et0=et0_val,
                        soil_moisture=soil_val,
                        source="open-meteo",
                    )
                )
                covered_dates.append(record_date)

            if new_rows:
                db.add_all(new_rows)
                db.commit()

            covered_set = set(covered_dates)
            missing_dates = [
                (start_date + timedelta(days=i)).isoformat()
                for i in range(expected_days)
                if (start_date + timedelta(days=i)) not in covered_set
            ]
            district_stats[district] = {
                "records": len(new_rows),
                "days_possible": expected_days,
                "covered_days": len(covered_set),
                "error": None,
                "missing_dates": missing_dates,
            }

        # Print coverage report per district.
        print(f"\n{'District':<35} {'Expected':>8} {'Covered':>7} {'Coverage':>8} {'Gap%':>6} {'New':>5}")
        print("-" * 76)
        all_covered = 0
        all_possible = 0
        for district in sorted(district_stats.keys()):
            s = district_stats[district]
            cov_pct = round(100 * s["covered_days"] / max(s["days_possible"], 1), 1)
            gap_pct = round(100 - cov_pct, 1)
            s["cov_pct"], s["gap_pct"] = cov_pct, gap_pct
            all_covered += s["covered_days"]
            all_possible += s["days_possible"]
            print(
                f"{district:<35} {s['days_possible']:>8} {s['covered_days']:>7} "
                f"{cov_pct:>7}% {gap_pct:>5}% {s['records']:>5}"
            )
        total_cov_pct = round(100 * all_covered / max(all_possible, 1), 1)
        print("-" * 76)
        print(f"{'TOTAL':<35} {all_possible:>8} {all_covered:>7} {total_cov_pct:>7}%")

        # Done condition: every district ≥ 95%, or list the gaps.
        gaps = [
            f"{d}: {district_stats[d]['cov_pct']}% coverage "
            f"({len(district_stats[d]['missing_dates'])} missing days)"
            for d in sorted(district_stats)
            if district_stats[d]["cov_pct"] < 95.0
        ]
        if gaps:
            print("\nCoverage gaps (< 95%):")
            for g in gaps:
                print(f"  - {g}")
            # Also list the actual missing dates for each gap district.
            for d in sorted(district_stats):
                if district_stats[d]["cov_pct"] < 95.0:
                    missing = district_stats[d]["missing_dates"]
                    preview = ", ".join(missing[:10])
                    if len(missing) > 10:
                        preview += f", ... (+{len(missing) - 10} more)"
                    print(f"  {d} missing dates: {preview or '(none returned)'}")
        else:
            print("\nEvery district has at least 95% daily coverage — requirement met!")

        return district_stats

    finally:
        if close_client:
            client.close()
        if close_db:
            db.close()


if __name__ == "__main__":
    main()

