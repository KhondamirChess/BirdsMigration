"""Reading and validating a GPS tracking CSV (Movebank-style columns).

Bad rows never stop the import: each one is dropped with a reason, counted in the
report and a few examples are kept with their line numbers. Only problems with the
file as a whole (empty, no header, a required column missing, nothing valid left)
raise DatasetFormatError.
"""
import csv
import io
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.errors import DatasetFormatError

# column name candidates, first match wins (Movebank names first)
COLUMNS = {
    "bird": ["individual-local-identifier", "tag-local-identifier", "individual_id", "bird_id", "id"],
    "time": ["timestamp", "datetime", "time"],
    "lat": ["location-lat", "latitude", "lat"],
    "lon": ["location-long", "longitude", "lon", "lng"],
    "species": ["individual-taxon-canonical-name", "species"],
    "event_id": ["event-id", "event_id"],
    "visible": ["visible"],
    "outlier": ["manually-marked-outlier", "algorithm-marked-outlier"],
    "study": ["study-name", "study"],
}
REQUIRED = ("bird", "time", "lat", "lon")

REASONS = {
    "no_id": "bird ID is empty",
    "bad_coord": "latitude / longitude missing, not a number or out of range",
    "null_island": "position 0, 0 (tag had no GPS fix)",
    "placeholder": "known placeholder position (tag had no GPS fix)",
    "hidden": "marked visible=false in Movebank",
    "outlier": "marked as an outlier in Movebank",
    "bad_time": "timestamp missing or not recognised",
    "duplicate": "same bird and timestamp as an earlier row",
}
SAMPLES_PER_REASON = 5


@dataclass
class TrackRecord:
    tag: str
    species: str | None
    ts: datetime
    lat: float
    lon: float
    event_id: str | None = None


@dataclass
class ParsedTracks:
    records: list[TrackRecord]
    study: str | None
    report: dict = field(default_factory=dict)


def _norm(name: str) -> str:
    """Normalise a column name for matching: lower case, letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_columns(headers: list[str], columns: dict[str, list[str]] = COLUMNS) -> dict[str, int]:
    """Map field keys to column indexes; case, spaces, '-' and '_' are ignored."""
    index = {}
    for i, h in enumerate(headers):
        index.setdefault(_norm(h), i)
    found = {}
    for key, names in columns.items():
        for name in names:
            if _norm(name) in index:
                found[key] = index[_norm(name)]
                break
    return found


def parse_number(v: str | None) -> float | None:
    """Convert text to a float; returns None if it is empty, not a number, NaN or infinite."""
    try:
        n = float((v or "").strip())
    except ValueError:
        return None
    return n if math.isfinite(n) else None


def parse_timestamp(v: str | None) -> datetime | None:
    """ISO 8601 / Movebank timestamps; times without a zone are UTC (Movebank exports are UTC)."""
    try:
        ts = datetime.fromisoformat((v or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def parse_tracking_csv(raw: bytes, placeholder_points: list[tuple[float, float]] = ()) -> ParsedTracks:
    """Read a tracking CSV, drop invalid rows with a reason and return the valid fixes plus an import report."""
    text = raw.decode("utf-8-sig", errors="replace")
    if not text.strip():
        raise DatasetFormatError("The file is empty.")
    reader = csv.reader(io.StringIO(text))
    headers = [h.strip() for h in next(reader)]
    cols = find_columns(headers)
    missing = [k for k in REQUIRED if k not in cols]
    if missing:
        raise DatasetFormatError("Required columns not found: " + ", ".join(missing) + ".",
                                 missing={k: COLUMNS[k] for k in missing}, headers=headers)

    placeholders = {(round(a, 4), round(b, 4)) for a, b in placeholder_points}
    rejected: Counter = Counter()
    samples: dict[str, list] = defaultdict(list)

    def reject(reason: str, line: int, value):
        """Count a dropped row under its reason and keep a few examples with line numbers."""
        rejected[reason] += 1
        if len(samples[reason]) < SAMPLES_PER_REASON:
            samples[reason].append({"line": line, "value": value})

    def cell(row: list[str], key: str) -> str | None:
        """Return the value of a field in a row, or None if the column or cell is missing."""
        i = cols.get(key)
        return row[i] if i is not None and i < len(row) else None

    by_bird: dict[str, list[tuple[int, TrackRecord]]] = defaultdict(list)
    study = None
    rows_read = 0
    for row in reader:
        line = reader.line_num
        if not row or all(not c.strip() for c in row):
            continue                                   # blank line, not a data row
        rows_read += 1
        tag = (cell(row, "bird") or "").strip()
        if not tag:
            reject("no_id", line, row[:6])
            continue
        if (cell(row, "visible") or "").strip().lower() == "false":
            reject("hidden", line, tag)
            continue
        if (cell(row, "outlier") or "").strip().lower() == "true":
            reject("outlier", line, tag)
            continue
        lat, lon = parse_number(cell(row, "lat")), parse_number(cell(row, "lon"))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            reject("bad_coord", line, [cell(row, "lat"), cell(row, "lon")])
            continue
        if lat == 0 and lon == 0:
            reject("null_island", line, [lat, lon])
            continue
        if (round(lat, 4), round(lon, 4)) in placeholders:
            reject("placeholder", line, [lat, lon])
            continue
        ts = parse_timestamp(cell(row, "time"))
        if ts is None:
            reject("bad_time", line, cell(row, "time"))
            continue
        study = study or (cell(row, "study") or "").strip() or None
        by_bird[tag].append((line, TrackRecord(tag, (cell(row, "species") or "").strip() or None, ts, lat, lon,
                                               (cell(row, "event_id") or "").strip() or None)))

    records: list[TrackRecord] = []
    for tag, fixes in by_bird.items():
        fixes.sort(key=lambda lf: lf[1].ts)            # playback needs increasing time per bird
        for k, (line, f) in enumerate(fixes):
            if k and fixes[k - 1][1].ts == f.ts:
                reject("duplicate", line, f"{tag} {f.ts.isoformat()}")
                continue
            records.append(f)

    if not records:
        raise DatasetFormatError("No valid GPS fixes left after validation.")
    return ParsedTracks(records, study, {
        "rows_read": rows_read,
        "rows_accepted": len(records),
        "rows_rejected": sum(rejected.values()),
        "birds": len(by_bird),
        "species": sorted({r.species for r in records if r.species}),
        "rejected": [{"reason": r, "label": REASONS[r], "count": n, "examples": samples[r]}
                     for r, n in rejected.most_common()],
    })
