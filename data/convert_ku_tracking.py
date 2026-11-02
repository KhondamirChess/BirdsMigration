"""Convert the KU tag export (Excel 2003 XML saved as .xls, one sheet per bird) to a Movebank-style CSV
that backend/scripts/import_dataset.py can load.

Every row is kept: rows without a GPS fix (position 0, 0) and repeated rows are dropped and counted by the importer.

Run from the project root:
  python data/convert_ku_tracking.py data/real_data/ku2025_oriental_magpie_tracking.xls
"""
import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SPECIES = "Oriental magpie"
STUDY = "KU 2025 Oriental magpie tracking"
NS = {"s": "urn:schemas-microsoft-com:office:spreadsheet"}
# export column -> Movebank column; the export also has a UTC+9 time, which is not used
FIELDS = {"Data ID": "individual-local-identifier", "Date(UTC)": "timestamp",
          "Decimal Latitude": "location-lat", "Decimal Longitude": "location-long"}


def cell_text(cell: ET.Element) -> str:
    """Return the text of a worksheet cell; header cells wrap it in <b>."""
    data = cell.find("s:Data", NS)
    return "".join(data.itertext()).strip() if data is not None else ""


def read_rows(path: Path) -> list[dict]:
    """Read all sheets into Movebank-style rows."""
    # the file declares EUC-KR, which the XML parser refuses, and uses the HTML entity &deg;
    text = path.read_bytes().decode("euc-kr", errors="replace")
    text = re.sub(r'encoding="[^"]*"', "", text, count=1).replace("&deg;", "°")
    rows = []
    for sheet in ET.fromstring(text).findall("s:Worksheet", NS):
        sheet_rows = [[cell_text(c) for c in r.findall("s:Cell", NS)] for r in sheet.findall(".//s:Row", NS)]
        cols = {name: sheet_rows[0].index(name) for name in FIELDS}
        for row in sheet_rows[1:]:
            rows.append({FIELDS[name]: row[i] for name, i in cols.items()}
                        | {"individual-taxon-canonical-name": SPECIES, "study-name": STUDY})
    return rows


def main() -> int:
    """Command-line entry point: write FILE.csv next to the given FILE.xls."""
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    rows = read_rows(src)
    out = src.with_suffix(".csv")
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{out}: {len(rows)} rows, {len({r['individual-local-identifier'] for r in rows})} birds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
