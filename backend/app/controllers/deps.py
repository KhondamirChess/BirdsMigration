from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.services.bird_service import BirdService
from app.services.dataset_service import DatasetService
from app.services.farm_service import FarmService


def dataset_service(session: Session = Depends(get_session)) -> DatasetService:
    """Create a DatasetService for the current request (FastAPI dependency)."""
    return DatasetService(session)


def bird_service(session: Session = Depends(get_session)) -> BirdService:
    """Create a BirdService for the current request (FastAPI dependency)."""
    return BirdService(session)


def farm_service(session: Session = Depends(get_session)) -> FarmService:
    """Create a FarmService for the current request (FastAPI dependency)."""
    return FarmService(session)
