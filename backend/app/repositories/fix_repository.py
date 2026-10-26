from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.models import Bird, Fix

CHUNK = 5000


class FixRepository:
    def __init__(self, session: Session):
        """Keep the database session used by all queries of this repository."""
        self.s = session

    def bulk_insert(self, rows: list[dict]) -> None:
        """rows: dicts with dataset_id, bird_id, ts, lat, lon, event_id."""
        for i in range(0, len(rows), CHUNK):
            self.s.execute(insert(Fix), rows[i:i + CHUNK])

    def track_rows(self, dataset_id: int):
        """(tag, species, ts, lat, lon) ordered by bird then time."""
        return self.s.execute(
            select(Bird.tag, Bird.species, Fix.ts, Fix.lat, Fix.lon)
            .join(Bird, Bird.id == Fix.bird_id)
            .where(Fix.dataset_id == dataset_id)
            .order_by(Bird.tag, Fix.ts)).all()
