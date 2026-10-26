import csv
import io

from sqlalchemy.orm import Session

from app.core.errors import DatasetFormatError
from app.repositories import FarmRepository
from app.services.track_parser import find_columns, parse_number

FARM_COLUMNS = {
    "code": ["farm_id", "code", "id"],
    "region": ["region"],
    "farm_type": ["farm_type", "type"],
    "lat": ["latitude", "lat"],
    "lon": ["longitude", "lon", "lng"],
}


class FarmService:
    def __init__(self, session: Session):
        """Set up the farm repository for this database session."""
        self.s = session
        self.farms = FarmRepository(session)

    def list_all(self) -> list[dict]:
        """Return all farms as dicts for the API."""
        return [{"farm_id": f.code, "region": f.region, "farm_type": f.farm_type,
                 "latitude": f.lat, "longitude": f.lon} for f in self.farms.all()]

    def import_csv(self, raw: bytes) -> dict:
        """Read a farm CSV, skip rows with invalid coordinates and save the rest; returns imported/skipped counts."""
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        if not rows:
            raise DatasetFormatError("The farm file is empty.")
        cols = find_columns(rows[0], FARM_COLUMNS)
        if "lat" not in cols or "lon" not in cols:
            raise DatasetFormatError("Farm file needs latitude and longitude columns.", headers=rows[0])
        farms, skipped = [], 0
        for k, r in enumerate(rows[1:], start=1):
            get = lambda key: r[cols[key]].strip() if key in cols and cols[key] < len(r) else ""
            lat, lon = parse_number(get("lat")), parse_number(get("lon"))
            if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                skipped += 1
                continue
            farms.append({"code": get("code") or f"F-{k:03d}", "region": get("region") or None,
                          "farm_type": get("farm_type") or None, "lat": lat, "lon": lon})
        self.farms.upsert_many(farms)
        self.s.commit()
        return {"imported": len(farms), "skipped": skipped}
