"""Spatial and geographic helpers for Andhra Pradesh grid."""
import math
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from backend.db import SessionLocal, ReferencePoint

# Approximate geographic bounding box for Andhra Pradesh (post-2022 reorganization)
AP_BOUNDING_BOX = {
    "min_lat": 12.5,
    "max_lat": 20.0,
    "min_lon": 76.5,
    "max_lon": 85.0,
}


def is_in_andhra_pradesh(lat: float, lon: float) -> bool:
    """Check if given coordinates fall within the approximate Andhra Pradesh bounding box."""
    return (
        AP_BOUNDING_BOX["min_lat"] <= lat <= AP_BOUNDING_BOX["max_lat"]
        and AP_BOUNDING_BOX["min_lon"] <= lon <= AP_BOUNDING_BOX["max_lon"]
    )


def check_ap_bounding_box(lat: float, lon: float) -> bool:
    """Alias for is_in_andhra_pradesh."""
    return is_in_andhra_pradesh(lat, lon)


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on the Earth in kilometers."""
    R = 6371.0  # Earth radius in kilometers
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def nearest_point(
    lat: float,
    lon: float,
    db: Optional[Session] = None,
    points: Optional[List[Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Find the nearest reference point (district headquarters) to the given (lat, lon).
    Returns a dict with district, lat, lon, source, and distance_km.
    """
    candidates = points
    close_db = False

    if candidates is None:
        if db is None:
            db = SessionLocal()
            close_db = True
        try:
            candidates = db.query(ReferencePoint).all()
        finally:
            if close_db:
                db.close()

    if not candidates:
        return None

    best_pt = None
    min_dist = float("inf")

    for pt in candidates:
        pt_lat = pt.lat if hasattr(pt, "lat") else pt["lat"]
        pt_lon = pt.lon if hasattr(pt, "lon") else pt["lon"]
        pt_dist_name = pt.district if hasattr(pt, "district") else pt["district"]
        pt_src = pt.source if hasattr(pt, "source") else pt.get("source", "open-meteo")

        dist = haversine_distance_km(lat, lon, pt_lat, pt_lon)
        if dist < min_dist:
            min_dist = dist
            best_pt = {
                "district": pt_dist_name,
                "lat": pt_lat,
                "lon": pt_lon,
                "source": pt_src,
                "distance_km": round(min_dist, 2),
            }

    return best_pt

