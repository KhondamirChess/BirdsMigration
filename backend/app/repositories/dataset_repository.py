from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Dataset, Fix


class DatasetRepository:
    def __init__(self, session: Session):
        """Keep the database session used by all queries of this repository."""
        self.s = session

    def list_with_counts(self):
        """Datasets with their bird / fix counts and time range."""
        return self.s.execute(
            select(Dataset,
                   func.count(Fix.id).label("n_fixes"),
                   func.count(func.distinct(Fix.bird_id)).label("n_birds"),
                   func.min(Fix.ts).label("start"),
                   func.max(Fix.ts).label("end"))
            .outerjoin(Fix, Fix.dataset_id == Dataset.id)
            .group_by(Dataset.id)
            .order_by(Dataset.position)).all()

    def get_by_slug(self, slug: str) -> Dataset | None:
        """Return the dataset with this slug, or None if there is none."""
        return self.s.scalar(select(Dataset).where(Dataset.slug == slug))

    def count(self) -> int:
        """Return the total number of datasets in the database."""
        return self.s.scalar(select(func.count(Dataset.id)))

    def add(self, dataset: Dataset) -> Dataset:
        """Save a new dataset and flush so that it gets its database id."""
        self.s.add(dataset)
        self.s.flush()
        return dataset

    def delete(self, dataset: Dataset) -> None:
        """Delete a dataset (its fixes are deleted with it by cascade)."""
        self.s.delete(dataset)
        self.s.flush()
