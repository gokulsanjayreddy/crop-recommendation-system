"""Farmer season history: GET/POST + one-time seed from generated CSV."""
import os
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.config import settings
from backend.db import SessionLocal, SeasonLog, engine, Base
from backend.schemas import SeasonLogIn, SeasonLogOut

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/api/history/{farmer_id}", response_model=list[SeasonLogOut])
def get_history(farmer_id: str, db: Session = Depends(get_db)):
    return db.query(SeasonLog).filter(
        SeasonLog.farmer_id == farmer_id).order_by(SeasonLog.year).all()


@router.post("/api/history", response_model=SeasonLogOut)
def log_season(log: SeasonLogIn, db: Session = Depends(get_db)):
    row = SeasonLog(**log.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def seed_from_csv(target_engine=None, session_factory=None):
    """Load farmer_seasons.csv into database once (idempotent)."""
    eng = target_engine or engine
    session_cls = session_factory or SessionLocal
    Base.metadata.create_all(eng)
    db = session_cls()
    try:
        if db.query(SeasonLog).count() > 0:
            return
        path = settings.DATA_DIR / "farmer_seasons.csv"
        df = pd.read_csv(path).fillna({"previous_crop": "",
                                       "profit_amount_rs_per_acre": None})
        rows = [SeasonLog(farmer_id=str(r["farmer_id"]),
                          farmer_name=(r["farmer_name"] if "farmer_name" in df.columns
                                       and pd.notna(r.get("farmer_name")) else None),
                          location_id=int(r["location_id"]),
                          season=r["season"], year=int(r["year"]),
                          soil_type=r["soil_type"],
                          previous_crop=r["previous_crop"] or "",
                          outcome=r["outcome"],
                          profit_amount_rs_per_acre=(
                              float(r["profit_amount_rs_per_acre"])
                              if pd.notna(r["profit_amount_rs_per_acre"]) else None),
                          next_crop_sown=r["next_crop_sown"])
                for _, r in df.iterrows()]
        db.add_all(rows)
        db.commit()
        print(f"seeded {len(rows)} season logs from farmer_seasons.csv")
    finally:
        db.close()
