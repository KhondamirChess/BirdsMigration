"""Routes the map simulator uses: datasets, their tracks, birds and farms."""
from fastapi import APIRouter, Depends

from app.controllers.deps import bird_service, dataset_service, farm_service
from app.schemas import BirdOut, ErrorOut, FarmOut, DatasetOut, Tracks
from app.services.bird_service import BirdService
from app.services.dataset_service import DatasetService
from app.services.farm_service import FarmService

router = APIRouter(prefix="/api", tags=["simulator"])


@router.get("/datasets", response_model=list[DatasetOut])
def list_datasets(svc: DatasetService = Depends(dataset_service)):
    """GET /api/datasets: return all datasets with their bird/fix counts and time range."""
    return svc.list_all()


@router.get("/datasets/{slug}/tracks", response_model=Tracks, responses={404: {"model": ErrorOut}})
def get_tracks(slug: str, svc: DatasetService = Depends(dataset_service)):
    """GET /api/datasets/{slug}/tracks: return every GPS fix of one dataset; 404 if the slug is unknown."""
    return svc.tracks(slug)


@router.get("/birds", response_model=list[BirdOut])
def list_birds(study: str | None = None, svc: BirdService = Depends(bird_service)):
    """GET /api/birds: return all birds (optionally only those of one study) with their statistics."""
    return svc.list_all(study)


@router.get("/farms", response_model=list[FarmOut])
def list_farms(svc: FarmService = Depends(farm_service)):
    """GET /api/farms: return all poultry farms with their coordinates."""
    return svc.list_all()
