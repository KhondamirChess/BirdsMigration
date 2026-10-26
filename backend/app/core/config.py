"""Settings read from environment variables or backend/.env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://hpai:hpai@localhost:5432/hpai"
    seed_demo_on_startup: bool = True
    demo_data_dir: Path = PROJECT_DIR / "data" / "demo_data"
    frontend_dir: Path = PROJECT_DIR / "frontend"
    # placeholder positions some tags write when they have no GPS fix (lat, lon); dropped on import.
    # 34.6888, 112.5154 appears 91 times in "Poultry network China 2022".
    placeholder_points: list[tuple[float, float]] = [(34.6888, 112.5154)]


@lru_cache
def get_settings() -> Settings:
    """Return the application settings; created once and cached for later calls."""
    return Settings()
