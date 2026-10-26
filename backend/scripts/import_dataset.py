"""Import any GPS tracking CSV (Movebank export or similar) into PostgreSQL.
The simulator lists every dataset in the database, so it shows up there after a page reload.

Run from backend/:
  python -m scripts.import_dataset "../data/real_data/Poultry network China 2022.csv"
  python -m scripts.import_dataset FILE --name "China 2022" --replace
"""
import argparse
from pathlib import Path

from app.core.database import SessionLocal, create_tables
from app.core.errors import DatasetFormatError
from app.services.dataset_service import DatasetService, slugify

POSITION_AFTER_DEMO = 100      # imported datasets are listed after the demo scenarios


def print_report(slug: str, r: dict) -> None:
    """Print how many rows of a dataset were imported and why the others were skipped."""
    print(f"{slug}: {r['birds']} birds ({', '.join(r['species']) or 'species unknown'}), "
          f"{r['rows_accepted']} of {r['rows_read']} rows imported")
    for x in r["rejected"]:
        lines = ", ".join(str(e["line"]) for e in x["examples"])
        print(f"  skipped {x['count']} × {x['label']} (lines {lines} …)")


def main() -> int:
    """Command-line entry point: import one CSV file as a dataset; returns the exit code."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path)
    ap.add_argument("--name", help="name shown in the simulator (default: file name)")
    ap.add_argument("--replace", action="store_true", help="replace a dataset with the same name")
    args = ap.parse_args()

    create_tables()
    with SessionLocal() as session:
        svc = DatasetService(session)
        slug = slugify(args.name or args.file.stem)
        if svc.exists(slug):
            if not args.replace:
                print(f"'{slug}' is already in the database; use --replace to load it again")
                return 1
            svc.delete(slug)
        try:
            slug, report = svc.import_csv(args.file.read_bytes(), args.file.name, slug=slug, name=args.name,
                                          meta={"position": POSITION_AFTER_DEMO})
        except DatasetFormatError as e:
            print(f"{args.file.name}: {e.message}")
            for k, v in e.details.items():
                print(f"  {k}: {v}")
            return 1
    print_report(slug, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
