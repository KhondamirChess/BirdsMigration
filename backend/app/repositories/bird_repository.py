from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Bird, Fix


class BirdRepository:
    def __init__(self, session: Session):
        """Keep the database session used by all queries of this repository."""
        self.s = session

    def get_or_create_many(self, study: str, species_by_tag: dict[str, str | None]) -> dict[str, int]:
        """Insert missing birds of a study and return {tag: bird id}."""
        if species_by_tag:
            self.s.execute(insert(Bird)
                           .values([{"study": study, "tag": t, "species": sp} for t, sp in species_by_tag.items()])
                           .on_conflict_do_nothing(constraint="uq_bird_study_tag"))
        return dict(self.s.execute(select(Bird.tag, Bird.id)
                                   .where(Bird.study == study, Bird.tag.in_(list(species_by_tag)))).all())

    def list_with_stats(self, study: str | None = None):
        """Birds with how many datasets / fixes they appear in."""
        q = (select(Bird,
                    func.count(func.distinct(Fix.dataset_id)).label("n_datasets"),
                    func.count(Fix.id).label("n_fixes"))
             .outerjoin(Fix, Fix.bird_id == Bird.id)
             .group_by(Bird.id)
             .order_by(Bird.study, func.length(Bird.tag), Bird.tag))
        if study:
            q = q.where(Bird.study == study)
        return self.s.execute(q).all()

    def count(self) -> int:
        """Return the total number of birds in the database."""
        return self.s.scalar(select(func.count(Bird.id)))

    def delete_orphans(self) -> None:
        """Remove birds that no longer have any fixes (after a dataset was deleted)."""
        self.s.execute(Bird.__table__.delete().where(~select(Fix.id).where(Fix.bird_id == Bird.id).exists()))
