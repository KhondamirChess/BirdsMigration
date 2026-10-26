from datetime import datetime

from pydantic import BaseModel


class Health(BaseModel):
    status: str
    datasets: int
    birds: int
    farms: int


class DatasetOut(BaseModel):
    slug: str
    name_en: str
    study: str
    species: list[str] = []
    name_ko: str | None = None
    desc_en: str | None = None
    desc_ko: str | None = None
    is_synthetic: bool
    source_file: str | None = None
    n_birds: int
    n_fixes: int
    start: datetime | None = None
    end: datetime | None = None


class TrackRecord(BaseModel):
    individual_id: str
    species: str | None
    timestamp: str
    latitude: float
    longitude: float


class Tracks(BaseModel):
    dataset: str
    name: str
    is_synthetic: bool
    records: list[TrackRecord]


class BirdOut(BaseModel):
    tag: str
    study: str
    species: str | None
    n_datasets: int
    n_fixes: int


class FarmOut(BaseModel):
    farm_id: str
    region: str | None
    farm_type: str | None
    latitude: float
    longitude: float


class ErrorOut(BaseModel):
    error: str
    message: str
    details: dict = {}
