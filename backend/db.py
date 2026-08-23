"""SQLite persistence (dev) via SQLAlchemy - swap-ready for Postgres."""
import os
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


class SeasonLog(Base):
    __tablename__ = "season_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    farmer_id = Column(String(32), index=True)
    farmer_name = Column(String(64), nullable=True)
    location_id = Column(Integer)
    season = Column(String(16))
    year = Column(Integer)
    soil_type = Column(String(32))
    previous_crop = Column(String(64), default="")
    outcome = Column(String(8))            # profit | loss
    profit_amount_rs_per_acre = Column(Float, nullable=True)
    next_crop_sown = Column(String(64))


def init_db():
    Base.metadata.create_all(engine)

