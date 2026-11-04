"""CLI and ingestion pipeline for Andhra Pradesh spatial and reference data."""
import sys
import time
import argparse
from typing import Optional, List, Tuple, Dict, Any
import httpx
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db import SessionLocal, ReferencePoint, init_db

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


if __name__ == "__main__":
    main()
