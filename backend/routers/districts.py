"""District reference points: GET /api/districts."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.db import get_db, ReferencePoint
from backend.schemas import DistrictOut

router = APIRouter()


@router.get("/api/districts", response_model=list[DistrictOut])
def get_districts(db: Session = Depends(get_db)):
    """Return all known Andhra Pradesh district reference points."""
    return db.query(ReferencePoint).order_by(ReferencePoint.district).all()
