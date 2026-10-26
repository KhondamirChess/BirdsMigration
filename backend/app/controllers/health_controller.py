from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.repositories import BirdRepository, DatasetRepository, FarmRepository
from app.schemas import Health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=Health)
def health(session: Session = Depends(get_session)):
    """GET /api/health: report that the API works and how many datasets, birds and farms are stored."""
    return {"status": "ok", "datasets": DatasetRepository(session).count(),
            "birds": BirdRepository(session).count(), "farms": FarmRepository(session).count()}
