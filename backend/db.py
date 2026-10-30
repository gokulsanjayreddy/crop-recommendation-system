"""Database configuration and models using SQLAlchemy 2."""
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

DEFAULT_POSTGRES_URL = "postgresql://postgres:postgres@localhost:5432/crop_db"
DEFAULT_SQLITE_URL = f"sqlite:///{(Path(__file__).resolve().parent / 'app.db').as_posix()}"


def _normalize_db_url(url: str) -> str:
    """Normalize legacy postgres:// scheme to postgresql:// for SQLAlchemy."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def resolve_database_url() -> str:
    """Resolve DATABASE_URL reading from environment (Postgres default, SQLite fallback for tests)."""
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return _normalize_db_url(env_url)

    # SQLite fallback when running tests
    if (
        "pytest" in sys.modules
        or os.getenv("PYTEST_CURRENT_TEST") is not None
        or os.getenv("TESTING", "").lower() in ("1", "true", "yes")
    ):
        return DEFAULT_SQLITE_URL

    configured = getattr(settings, "DATABASE_URL", DEFAULT_POSTGRES_URL)
    return _normalize_db_url(configured)


DATABASE_URL = resolve_database_url()


def create_db_engine(url: str = DATABASE_URL):
    """Create a SQLAlchemy engine configured for SQLite or PostgreSQL."""
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine_kwargs = {"connect_args": connect_args}
    if not url.startswith("sqlite"):
        engine_kwargs["pool_pre_ping"] = True
    return create_engine(url, **engine_kwargs)


engine = create_db_engine(DATABASE_URL)
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


def init_db(target_engine=None):
    Base.metadata.create_all(target_engine or engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
