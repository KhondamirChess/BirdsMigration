"""Load the synthetic demo data (data/demo_data: 3 scenarios, farms) into PostgreSQL.

Run from backend/:  python -m scripts.seed_demo [--reset]
  --reset  delete the scenarios first and load them again
"""
import json
import sys

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal, create_tables
from app.repositories import DatasetRepository
from app.services.dataset_service import DEMO_STUDY, DatasetService
from app.services.farm_service import FarmService
from scripts.import_dataset import print_report


def seed(session: Session, settings: Settings, reset: bool = False) -> None:
    """Load the demo farms and the three demo scenarios into the database (reset=True reloads them)."""
    folder = settings.demo_data_dir
    meta = json.loads((folder / "scenarios.json").read_text())
    datasets = DatasetService(session)
    farms = FarmService(session).import_csv((folder / meta["farms_file"]).read_bytes())
    print(f"farms: {farms['imported']} imported, {farms['skipped']} skipped")
    for pos, scn in enumerate(meta["scenarios"]):
        if datasets.exists(scn["id"]):
            if not reset:
                print(f"{scn['id']}: already in the database, skipped")
                continue
            datasets.delete(scn["id"])
        slug, report = datasets.import_csv(
            (folder / scn["file"]).read_bytes(), scn["file"], slug=scn["id"], name=scn["name_en"], study=DEMO_STUDY,
            meta={"position": pos, "name_ko": scn["name_ko"], "desc_en": scn["desc_en"], "desc_ko": scn["desc_ko"],
                  "is_synthetic": True})
        print_report(slug, report)


def seed_if_empty(session: Session, settings: Settings) -> None:
    """Load the demo data only if the database has no datasets yet (used at server startup)."""
    if DatasetRepository(session).count() == 0 and (settings.demo_data_dir / "scenarios.json").exists():
        seed(session, settings)


if __name__ == "__main__":
    create_tables()
    with SessionLocal() as s:
        seed(s, get_settings(), reset="--reset" in sys.argv)
