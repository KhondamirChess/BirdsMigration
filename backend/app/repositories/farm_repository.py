from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Farm


class FarmRepository:
    def __init__(self, session: Session):
        """Keep the database session used by all queries of this repository."""
        self.s = session

    def all(self) -> list[Farm]:
        """Return all farms ordered by their code."""
        return list(self.s.scalars(select(Farm).order_by(Farm.code)))

    def count(self) -> int:
        """Return the total number of farms in the database."""
        return self.s.scalar(select(func.count(Farm.id)))

    def upsert_many(self, farms: list[dict]) -> None:
        """Insert farms, updating existing ones with the same code."""
        if not farms:
            return
        stmt = insert(Farm).values(farms)
        self.s.execute(stmt.on_conflict_do_update(
            index_elements=[Farm.code],
            set_={c: stmt.excluded[c] for c in ("region", "farm_type", "lat", "lon")}))
