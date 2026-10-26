import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models import Dataset
from app.repositories import BirdRepository, DatasetRepository, FixRepository
from app.services.track_parser import parse_tracking_csv

DEMO_STUDY = "HPAI demo (synthetic)"


def slugify(text: str) -> str:
    """Turn a name into a URL-safe id, e.g. 'China 2022' -> 'china-2022' (max 48 characters)."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "dataset"


class DatasetService:
    def __init__(self, session: Session):
        """Set up the dataset, bird and fix repositories for this database session."""
        self.s = session
        self.datasets = DatasetRepository(session)
        self.birds = BirdRepository(session)
        self.fixes = FixRepository(session)

    def list_all(self) -> list[dict]:
        """Return all datasets as dicts for the API, with counts, species and time range."""
        return [{"slug": d.slug, "name_en": d.name_en, "name_ko": d.name_ko, "desc_en": d.desc_en,
                 "desc_ko": d.desc_ko, "study": d.study, "is_synthetic": d.is_synthetic,
                 "source_file": d.source_file, "species": d.import_report.get("species", []),
                 "n_birds": nb, "n_fixes": nf, "start": st, "end": en}
                for d, nf, nb, st, en in self.datasets.list_with_counts()]

    def get(self, slug: str) -> Dataset:
        """Return the dataset with this slug or raise NotFoundError (HTTP 404)."""
        d = self.datasets.get_by_slug(slug)
        if d is None:
            raise NotFoundError(f"Dataset '{slug}' not found.", slug=slug)
        return d

    def tracks(self, slug: str) -> dict:
        """Return all GPS fixes of a dataset in the format the map simulator plays back."""
        d = self.get(slug)
        return {"dataset": slug, "name": d.source_file or slug, "is_synthetic": d.is_synthetic,
                "records": [{"individual_id": tag, "species": sp, "timestamp": ts.isoformat().replace("+00:00", "Z"),
                             "latitude": lat, "longitude": lon}
                            for tag, sp, ts, lat, lon in self.fixes.track_rows(d.id)]}

    def import_csv(self, raw: bytes, filename: str, *, slug: str | None = None, name: str | None = None,
                   study: str | None = None, meta: dict | None = None) -> tuple[str, dict]:
        """Validate a tracking CSV and store it as a dataset. Returns (slug, import report)."""
        parsed = parse_tracking_csv(raw, get_settings().placeholder_points)
        stem = Path(filename).stem
        study = study or parsed.study or stem
        slug = slug or slugify(name or stem)
        d = self.datasets.add(Dataset(slug=slug, name_en=name or stem, study=study,
                                      source_file=Path(filename).name, import_report=parsed.report, **(meta or {})))
        species = {}
        for r in parsed.records:
            species.setdefault(r.tag, r.species)
        ids = self.birds.get_or_create_many(study, species)
        self.fixes.bulk_insert([{"dataset_id": d.id, "bird_id": ids[r.tag], "ts": r.ts, "lat": r.lat,
                                 "lon": r.lon, "event_id": r.event_id} for r in parsed.records])
        self.s.commit()
        return slug, parsed.report

    def exists(self, slug: str) -> bool:
        """Return True if a dataset with this slug is already stored."""
        return self.datasets.get_by_slug(slug) is not None

    def delete(self, slug: str) -> None:
        """Delete a dataset, then remove birds that are left without any fixes."""
        self.datasets.delete(self.get(slug))
        self.birds.delete_orphans()
        self.s.commit()
