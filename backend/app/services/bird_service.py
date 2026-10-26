from sqlalchemy.orm import Session

from app.repositories import BirdRepository


class BirdService:
    def __init__(self, session: Session):
        """Set up the bird repository for this database session."""
        self.birds = BirdRepository(session)

    def list_all(self, study: str | None = None) -> list[dict]:
        """Return birds (optionally of one study) as dicts for the API, with dataset and fix counts."""
        return [{"tag": b.tag, "study": b.study, "species": b.species, "n_datasets": nd, "n_fixes": nf}
                for b, nd, nf in self.birds.list_with_stats(study)]
