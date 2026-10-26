"""Generate synthetic demo data for the Bird-HPAI risk simulator.

Outputs (in ./demo_data):
  - scenario_1_baseline.csv, scenario_2_coldwave.csv, scenario_3_spring.csv
      the SAME 20 mallards (Anas platyrhynchos) in three scenarios,
      Movebank-style columns, one GPS fix every 2 hours
  - farms.csv   synthetic poultry farm locations
  - scenarios.json  scenario names/descriptions; backend/scripts/seed_demo.py loads
      them together with the CSVs into PostgreSQL

Wetland and region coordinates are approximate real places; every track and
farm generated around them is synthetic and must not be read as real data.

Run:  python generate_demo_data.py
"""
import csv
import io
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SPECIES = "Anas platyrhynchos"
N_BIRDS = 20
BIRD_IDS = [f"MAL-{i:02d}" for i in range(1, N_BIRDS + 1)]
FIX_HOURS = 2
BUFFER_KM = 3.0
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).parent
OUT = ROOT / "demo_data"

# approximate wetland / stopover locations (lat, lon)
SITES = {
    "imjin": (37.93, 126.72),        # Imjin River, Paju
    "han_estuary": (37.73, 126.63),  # Han River estuary, Gimpo
    "cheorwon": (38.20, 127.25),     # Cheorwon plain
    "sapgyo": (36.88, 126.83),       # Sapgyo Lake
    "asan": (36.91, 126.95),         # Asan Lake
    "ganwol": (36.62, 126.42),       # Ganwol Lake, Cheonsu Bay
    "geum": (36.03, 126.78),         # Geum River estuary
    "mangyeong": (35.87, 126.78),    # Mangyeong River
    "dongjin": (35.79, 126.74),      # Dongjin River
    "yeongsan": (34.79, 126.47),     # Yeongsan Lake
    "yalu": (39.85, 124.15),         # Yalu River estuary
    "liaoning": (40.85, 121.85),     # Liao River delta
    "songnen": (46.50, 124.40),      # Songnen plain
    "khanka": (45.00, 132.40),       # Lake Khanka
}

# synthetic poultry farm clusters: (region, centre, number of farms, farm type)
FARM_CLUSTERS = [
    ("Paju", (37.80, 126.82), 2, "layer"),
    ("Icheon", (37.27, 127.44), 2, "layer"),
    ("Cheonan", (36.82, 127.15), 4, "layer"),
    ("Asan", (36.80, 126.98), 3, "broiler"),
    ("Eumseong", (36.94, 127.69), 3, "duck"),
    ("Iksan", (35.96, 127.00), 4, "broiler"),
    ("Gimje", (35.80, 126.90), 6, "layer"),
    ("Naju", (35.02, 126.72), 5, "duck"),
    ("Yeongam", (34.82, 126.62), 3, "duck"),
]


# ---------- geometry ----------
def offset(p, km, bearing_deg):
    """Point `km` away from p=(lat, lon) on the given bearing (flat-earth, fine at < 50 km)."""
    lat, lon = p
    b = math.radians(bearing_deg)
    return (lat + km * math.cos(b) / 111.32,
            lon + km * math.sin(b) / (111.32 * math.cos(math.radians(lat))))


def dist_km(a, b):
    """Great-circle (haversine) distance in km between two (lat, lon) points."""
    r = math.pi / 180
    h = (math.sin((b[0] - a[0]) * r / 2) ** 2
         + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin((b[1] - a[1]) * r / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


def jitter(rng, p, km):
    """Return a random point near p; the distance is normally distributed with spread `km`."""
    return offset(p, abs(rng.gauss(0, km)), rng.uniform(0, 360))


# ---------- farms ----------
def make_farms(rng):
    """Create the synthetic farms: random points around each cluster centre in FARM_CLUSTERS."""
    farms = []
    for region, centre, n, ftype in FARM_CLUSTERS:
        for _ in range(n):
            lat, lon = offset(centre, rng.uniform(0.5, 6), rng.uniform(0, 360))
            farms.append({"farm_id": f"F-{len(farms) + 1:02d}", "region": region, "farm_type": ftype,
                          "latitude": round(lat, 5), "longitude": round(lon, 5)})
    return farms


def farm_pt(f):
    """Return the (lat, lon) of a farm dict."""
    return (f["latitude"], f["longitude"])


# ---------- bird movement ----------
def local_hour(t):
    """Hour of the day in Korean time (KST) as a decimal number, e.g. 18.5 for 18:30."""
    lt = t.astimezone(KST)
    return lt.hour + lt.minute / 60


def night_key(t):
    """Local date the current night started on (fixes before 05:00 belong to the previous evening)."""
    lt = t.astimezone(KST)
    return (lt - timedelta(hours=5)).date()


def evening(day, hour=18):
    """18:00 KST on a date, as UTC: ducks leave on migration in the evening."""
    return datetime(day.year, day.month, day.day, hour, tzinfo=KST).astimezone(timezone.utc)


def random_fields(rng, roost, n=2, km=(3, 11), bearings=(20, 160)):
    """Feeding fields around a roost; default bearings point inland (east) from the west coast."""
    return [offset(roost, rng.uniform(*km), rng.uniform(*bearings)) for _ in range(n)]


def field_near_farm(rng, farm):
    """A feeding field 0.8-2.5 km from a farm, i.e. inside its 3 km buffer."""
    return offset(farm_pt(farm), rng.uniform(0.8, 2.5), rng.uniform(0, 360))


def stay(rng, site, fields=None, until=None, roost_km=1.2):
    """Plan one stay at a site: a roost near it, feeding fields around it and the time the bird leaves."""
    roost = jitter(rng, SITES[site], roost_km)
    return {"roost": roost, "fields": fields if fields is not None else random_fields(rng, roost), "until": until}


def simulate(rng, start, end, stays):
    """GPS fixes every FIX_HOURS: daytime at the roost, nights in a feeding field,
    commuting at dawn/dusk, and straight-ish night flights between stays."""
    out = []
    t = start + timedelta(minutes=rng.uniform(0, 110))
    step = lambda: timedelta(hours=FIX_HOURS, minutes=rng.gauss(0, 2))
    night_field = {}
    i = 0
    while t < end:
        s = stays[i]
        if s["until"] is not None and t >= s["until"] and i + 1 < len(stays):
            a, b = s["roost"], stays[i + 1]["roost"]
            d = dist_km(a, b)
            dur = d / rng.uniform(45, 65)            # hours, ground speed km/h
            bend = rng.gauss(0, 0.05) * d / 111.32   # sideways drift, degrees
            dep = s["until"]
            while t < end and (t - dep).total_seconds() / 3600 < dur:
                f = (t - dep).total_seconds() / 3600 / dur
                sway = math.sin(math.pi * f) * bend
                out.append((t, a[0] + (b[0] - a[0]) * f + sway * 0.5, a[1] + (b[1] - a[1]) * f - sway))
                t += step()
            i += 1
            continue
        h = local_hour(t)
        k = (i, night_key(t))
        if k not in night_field:
            night_field[k] = rng.choice(s["fields"])
        field = night_field[k]
        roost = s["roost"]
        if 7 <= h < 17:
            p = jitter(rng, roost, 0.25)
        elif 17 <= h < 19:
            f = (h - 17) / 2
            p = (roost[0] + (field[0] - roost[0]) * f, roost[1] + (field[1] - roost[1]) * f)
        elif 5 <= h < 7:
            f = (h - 5) / 2
            p = (field[0] + (roost[0] - field[0]) * f, field[1] + (roost[1] - field[1]) * f)
        else:
            p = jitter(rng, field, 0.3)
        if rng.random() > 0.01:                       # ~1% missed fixes, like real tags
            out.append((t, p[0], p[1]))
        t += step()
    return out


# ---------- scenarios ----------
def scenario_baseline(rng, farms):
    """Normal wintering: birds stay at central-west wetlands all season; 2 birds feed near a farm."""
    start, end = datetime(2025, 12, 1, tzinfo=timezone.utc), datetime(2026, 1, 31, tzinfo=timezone.utc)
    sites = ["sapgyo"] * 5 + ["asan"] * 4 + ["geum"] * 4 + ["mangyeong"] * 4 + ["ganwol"] * 3
    by_region = lambda r: [f for f in farms if f["region"] == r]
    plans = {}
    for bid, site in zip(BIRD_IDS, sites):
        s = stay(rng, site)
        plans[bid] = [s]
    # incidental contact: one Asan Lake bird and one Mangyeong bird use a field next to a farm
    plans["MAL-06"][0]["fields"][1] = field_near_farm(rng, by_region("Asan")[0])
    plans["MAL-15"][0]["fields"][1] = field_near_farm(rng, by_region("Gimje")[0])
    return start, end, plans


def scenario_coldwave(rng, farms):
    """Cold wave on 27-30 Dec freezes northern wetlands: 12 northern birds and the
    4 Geum birds shift south into the farm-dense Gimje / Naju / Yeongam area."""
    start, end = datetime(2025, 12, 1, tzinfo=timezone.utc), datetime(2026, 1, 31, tzinfo=timezone.utc)
    by_region = lambda r: [f for f in farms if f["region"] == r]
    north = ["imjin"] * 4 + ["han_estuary"] * 4 + ["cheorwon"] * 4
    dest = ["mangyeong"] * 4 + ["dongjin"] * 4 + ["yeongsan"] * 4
    dest_farms = {"mangyeong": by_region("Gimje") + by_region("Iksan"),
                  "dongjin": by_region("Gimje"),
                  "yeongsan": by_region("Naju") + by_region("Yeongam")}
    plans = {}
    for k, bid in enumerate(BIRD_IDS):
        if k < 12:
            dep = evening(datetime(2025, 12, 27 + rng.randint(0, 3)).date())
            near = rng.choice(dest_farms[dest[k]])
            d_stay = stay(rng, dest[k])
            d_stay["fields"] = [field_near_farm(rng, near), d_stay["fields"][0]]
            plans[bid] = [stay(rng, north[k], until=dep), d_stay]
        elif k < 16:
            plans[bid] = [stay(rng, "sapgyo")]       # control group: unaffected
        else:
            dep = evening(datetime(2026, 1, 2 + rng.randint(0, 2)).date())
            d_stay = stay(rng, "mangyeong")
            d_stay["fields"] = [field_near_farm(rng, rng.choice(dest_farms["mangyeong"])), d_stay["fields"][0]]
            plans[bid] = [stay(rng, "geum", until=dep), d_stay]
    return start, end, plans


def scenario_spring(rng, farms):
    """Spring departure: birds winter at central wetlands, then leave Korea between
    20 Feb and 18 Mar via the Han estuary / Yalu estuary to NE China and Russia."""
    start, end = datetime(2026, 2, 1, tzinfo=timezone.utc), datetime(2026, 4, 10, tzinfo=timezone.utc)
    by_region = lambda r: [f for f in farms if f["region"] == r]
    sites = ["geum"] * 5 + ["mangyeong"] * 5 + ["sapgyo"] * 5 + ["asan"] * 5
    finals = ["liaoning", "songnen", "khanka", "songnen"] * 5
    plans = {}
    for k, (bid, site) in enumerate(zip(BIRD_IDS, sites)):
        t = datetime(2026, 2, 20).date() + timedelta(days=rng.randint(0, 26))
        winter = stay(rng, site, until=evening(t))
        legs = [winter]
        if k % 2 == 0:                               # half of them refuel at the Han estuary
            t += timedelta(days=rng.randint(3, 8))
            legs.append(stay(rng, "han_estuary", until=evening(t)))
        t += timedelta(days=rng.randint(5, 10))
        legs.append(stay(rng, "yalu", until=evening(t)))
        legs.append(stay(rng, finals[k], roost_km=8))
        for s in legs[1:]:
            s["fields"] = random_fields(rng, s["roost"], km=(3, 9), bearings=(0, 360))
        plans[bid] = legs
    # three birds feed next to farms before leaving: risk falls as the birds depart
    winter_fields = lambda b: plans[b][0]["fields"]
    winter_fields("MAL-02")[1] = field_near_farm(rng, by_region("Iksan")[1])
    winter_fields("MAL-08")[1] = field_near_farm(rng, by_region("Gimje")[2])
    winter_fields("MAL-18")[1] = field_near_farm(rng, by_region("Asan")[1])
    return start, end, plans


SCENARIOS = [
    {"id": "baseline", "file": "scenario_1_baseline.csv", "build": scenario_baseline,
     "name_en": "Baseline wintering", "name_ko": "평상시 월동",
     "desc_en": "Dec–Jan. All 20 mallards stay at their central-west wetlands and fly out to feed at night. Only 5 of the 20 birds come within 3 km of a farm. Low risk.",
     "desc_ko": "12월–1월. 20마리 모두 중서부 습지에 머물며 밤에 먹이터로 이동합니다. 농장 3 km 안에 들어오는 개체는 20마리 중 5마리뿐입니다. 위험 낮음."},
    {"id": "coldwave", "file": "scenario_2_coldwave.csv", "build": scenario_coldwave,
     "name_en": "Cold wave shift", "name_ko": "한파 남하",
     "desc_en": "Dec–Jan. A cold wave on 27–30 Dec freezes northern wetlands. 16 birds move south into the farm-dense Gimje–Naju area and feed near poultry farms. High risk after the cold wave.",
     "desc_ko": "12월–1월. 12월 27–30일 한파로 북부 습지가 얼어붙습니다. 16마리가 농장이 밀집한 김제–나주 지역으로 남하해 가금농장 근처에서 먹이를 찾습니다. 한파 이후 위험 높음."},
    {"id": "spring", "file": "scenario_3_spring.csv", "build": scenario_spring,
     "name_en": "Spring departure", "name_ko": "봄철 북상",
     "desc_en": "Feb–Apr. The birds leave Korea between 20 Feb and 18 Mar via the Han and Yalu estuaries to NE China and Russia. Farm contact falls as they leave.",
     "desc_ko": "2월–4월. 2월 20일–3월 18일 사이에 한강·압록강 하구를 거쳐 중국 동북부와 러시아로 떠납니다. 개체가 떠나면서 농장 접촉이 줄어듭니다."},
]

HEADER = ["event-id", "individual-local-identifier", "individual-taxon-canonical-name",
          "timestamp", "location-lat", "location-long"]


def build_tracks(scn, farms, seed):
    """Generate all rows of one scenario CSV: every bird's GPS fixes with event ids."""
    rng = random.Random(seed)
    start, end, plans = scn["build"](rng, farms)
    rows = []
    for bid in BIRD_IDS:
        for t, lat, lon in simulate(rng, start, end, plans[bid]):
            rows.append([bid, SPECIES, t.strftime("%Y-%m-%d %H:%M:%S"), round(lat, 6), round(lon, 6)])
    return [[i + 1, *r] for i, r in enumerate(rows)]


# ---------- checks ----------
def check(name, rows, farms):
    """Fail loudly if a scenario would not display or play back correctly."""
    by = {}
    for _, bid, sp, ts, lat, lon in rows:
        assert sp == SPECIES, f"{name}: unexpected species {sp}"
        assert -90 <= lat <= 90 and -180 <= lon <= 180, f"{name}: bad coordinate {lat},{lon}"
        by.setdefault(bid, []).append((datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"), lat, lon))
    assert sorted(by) == BIRD_IDS, f"{name}: expected {N_BIRDS} birds, got {len(by)}"
    max_gap = max_speed = 0.0
    for bid, fx in by.items():
        for (t0, *a), (t1, *b) in zip(fx, fx[1:]):
            hrs = (t1 - t0).total_seconds() / 3600
            assert hrs > 0, f"{name}: {bid} timestamps not increasing at {t1}"
            max_gap = max(max_gap, hrs)
            max_speed = max(max_speed, dist_km(a, b) / hrs)
    assert max_gap < 12, f"{name}: gap of {max_gap:.1f} h"
    assert max_speed < 100, f"{name}: implied speed {max_speed:.0f} km/h"
    contact_birds, contact_farms, contact_fixes = set(), set(), 0
    for _, bid, _, _, lat, lon in rows:
        for f in farms:
            if dist_km((lat, lon), farm_pt(f)) <= BUFFER_KM:
                contact_birds.add(bid)
                contact_farms.add(f["farm_id"])
                contact_fixes += 1
                break
    first, last = min(r[3] for r in rows), max(r[3] for r in rows)
    print(f"  {name:<24} {len(by)} birds  {len(rows):>6} fixes  {first[:10]} → {last[:10]}  "
          f"max gap {max_gap:.1f} h  max speed {max_speed:.0f} km/h  |  "
          f"in {BUFFER_KM:g} km buffer: {len(contact_birds):>2} birds, {len(contact_farms):>2} farms, {contact_fixes} fixes")


def to_csv(header, rows):
    """Return the header and rows as CSV text."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def main():
    """Generate farms.csv, the three scenario CSVs and scenarios.json in demo_data/."""
    OUT.mkdir(exist_ok=True)
    farms = make_farms(random.Random(42))
    farm_csv = to_csv(list(farms[0]), [list(f.values()) for f in farms])
    (OUT / "farms.csv").write_text(farm_csv)
    print(f"farms.csv: {len(farms)} synthetic farms in {len(FARM_CLUSTERS)} regions")

    meta = {"note": "Synthetic demo data generated by generate_demo_data.py, not real tracking or farm records.",
            "species": SPECIES, "bufferKm": BUFFER_KM, "farms_file": "farms.csv", "scenarios": []}
    for k, scn in enumerate(SCENARIOS):
        rows = build_tracks(scn, farms, seed=100 + k)
        check(scn["file"], rows, farms)
        (OUT / scn["file"]).write_text(to_csv(HEADER, rows))
        meta["scenarios"].append({key: scn[key] for key in ("id", "file", "name_en", "name_ko", "desc_en", "desc_ko")})
    (OUT / "scenarios.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {OUT}/ (load it into the database with backend/scripts/seed_demo.py)")

if __name__ == "__main__":
    main()
