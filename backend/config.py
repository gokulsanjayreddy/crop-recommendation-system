"""Application configuration using pydantic-settings."""
from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database connection URL (default PostgreSQL, SQLite fallback for tests)
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/crop_db",
        description="SQLAlchemy database connection URL",
    )

    # Directory paths
    BASE_DIR: Path = Field(default=BASE_DIR, description="Root directory of the project")
    MODEL_DIR: Path = Field(
        default_factory=lambda: BASE_DIR / "models",
        description="Directory containing trained model artifacts (.pkl, metadata.json)",
    )
    DATA_DIR: Path = Field(
        default_factory=lambda: BASE_DIR / "data",
        description="Directory containing datasets (.csv)",
    )
    FRONTEND_DIR: Path = Field(
        default_factory=lambda: BASE_DIR / "frontend" / "standalone",
        description="Directory containing standalone frontend assets",
    )

    # Network / external API timeouts (in seconds)
    HTTP_TIMEOUT: float = Field(default=10.0, description="Default HTTP client timeout in seconds")
    OPEN_METEO_TIMEOUT: float = Field(default=10.0, description="Open-Meteo API timeout in seconds")
    NASA_POWER_TIMEOUT: float = Field(default=30.0, description="NASA POWER API timeout in seconds")
    SOILGRIDS_TIMEOUT: float = Field(default=15.0, description="ISRIC SoilGrids API timeout in seconds")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
