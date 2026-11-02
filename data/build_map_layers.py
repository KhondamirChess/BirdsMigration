"""Build the offline base map in frontend/geo/: shaded relief images and map_layers.js (coast, rivers, lakes, names).

Run once, the output is committed:  python data/build_map_layers.py --cache DIR
Needs: numpy pillow shapely (build-time only, the app itself does not use them).

Sources: Natural Earth (public domain), OpenStreetMap via Overpass (ODbL) for Korea, Terrain Tiles on AWS for elevation.
"""
import argparse
import io
import json
import math
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from shapely import make_valid
from shapely.geometry import LineString, MultiLineString, Polygon, box, shape
from shapely.ops import linemerge, polygonize, unary_union

OUT = Path(__file__).resolve().parent.parent / "frontend" / "geo"
NE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/{}.geojson"
TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

REGION = box(95, 15, 150, 58)          # detailed coastline and borders
KOREA = box(124, 33, 131.2, 43.2)      # rivers and lakes from OpenStreetMap
# (zoom, lon0, lat0, lon1, lat1, relief exaggeration, map zoom to start loading at)
RELIEF = [(4, -180, -85.05, 180, 85.05, 9, 0), (6, 95, 15, 150, 58, 5, 4),
          (8, 118, 30, 136, 48, 2.5, 16), (10, 125.7, 33, 129.6, 38.7, 1.5, 65)]

# hypsometric tint: elevation (m) -> colour, opacity
TINT = [(0, (150, 180, 130), 0.0), (150, (163, 190, 137), 0.30), (500, (205, 205, 150), 0.50),
        (1000, (200, 170, 120), 0.62), (2000, (170, 130, 100), 0.72), (4000, (190, 175, 170), 0.80),
        (6000, (245, 245, 245), 0.88)]

# Natural Earth has no Korean river names and uses old romanizations for Korean peaks
RIVER_KO = {"Yangtze": "창장강", "Chang Jiang": "창장강", "Huang": "황허강", "Amur": "아무르강", "Songhua": "쑹화강",
            "Liao": "랴오허강", "Mekong": "메콩강", "Xi": "시장강", "Huai": "화이허강", "Ussuri": "우수리강"}
OSM_RIVER_EN = {"남한강": "Namhan River", "섬진강": "Seomjin River", "남대천": "Namdae Stream", "충만강": "Chungman River"}
PEAK_FIX = {"Sorak-san": ("Seoraksan", "설악산"), "Chiri-san": ("Jirisan", "지리산"),
            "Halla-san": ("Hallasan", "한라산"), "Paektu-san": ("Baekdusan", "백두산")}
EXTRA_PEAKS = [("Deogyusan", "덕유산", 127.75, 35.86, 1614), ("Songnisan", "속리산", 127.87, 36.54, 1058),
               ("Taebaeksan", "태백산", 128.92, 37.10, 1567), ("Odaesan", "오대산", 128.54, 37.79, 1565),
               ("Bukhansan", "북한산", 126.98, 37.66, 836), ("Gayasan", "가야산", 128.12, 35.82, 1430),
               ("Gyeryongsan", "계룡산", 127.21, 36.34, 847), ("Naejangsan", "내장산", 126.89, 35.48, 763)]
RANGES = [("Taebaek Mountains", "태백산맥", 128.95, 37.35), ("Sobaek Mountains", "소백산맥", 127.85, 36.05),
          ("Charyeong Mountains", "차령산맥", 127.0, 36.7), ("Noryeong Mountains", "노령산맥", 127.0, 35.55),
          ("Hamgyong Mountains", "함경산맥", 128.6, 41.3), ("Nangnim Mountains", "낭림산맥", 126.9, 40.7)]


def fetch(url, path, data=None):
    """Download url into the cache once."""
    if not path.exists() or not path.stat().st_size:
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "hpai-lab-map-build"})
        with urllib.request.urlopen(req, timeout=300) as r:
            path.write_bytes(r.read())
    return path


def natural_earth(cache, name):
    """Return the features of a Natural Earth layer that have a geometry; property names are lower-cased."""
    data = json.loads(fetch(NE_URL.format(name), cache / f"{name}.geojson").read_text(encoding="utf-8"))
    return [({k.lower(): v for k, v in f["properties"].items()}, make_valid(shape(f["geometry"])))
            for f in data["features"] if f["geometry"] and f["geometry"]["coordinates"]]


def overpass(cache, name, query):
    """Run an Overpass query once and return its elements."""
    data = urllib.parse.urlencode({"data": query}).encode()
    return json.loads(fetch(OVERPASS_URL, cache / f"{name}.json", data).read_text(encoding="utf-8"))["elements"]


def rings(geom, digits=3):
    """Flatten any geometry to a list of [lon, lat, lon, lat, ...] rings or lines."""
    out = []
    if geom.is_empty:
        return out
    if hasattr(geom, "geoms"):
        for g in geom.geoms:
            out += rings(g, digits)
    elif isinstance(geom, Polygon):
        for r in [geom.exterior, *geom.interiors]:
            out += rings(LineString(r.coords), digits)
    elif isinstance(geom, LineString):
        out.append([round(v, digits) for xy in geom.coords for v in xy[:2]])
    return out


def km_len(line):
    """Approximate length of a lon/lat line in km."""
    c = np.array(line.coords)
    dx = np.diff(c[:, 0]) * np.cos(np.radians(c[:-1, 1]))
    return float(np.hypot(dx, np.diff(c[:, 1])).sum() * 111.2)


def km2_area(poly):
    """Approximate area of a lon/lat polygon in km2."""
    return poly.area * 111.2 ** 2 * math.cos(math.radians(poly.representative_point().y))


def add_label(labels, kind, en, ko, point, min_k, ele=None):
    """Add a map name; min_k is the map zoom it appears at. An empty en hides it in the English map."""
    item = {"t": kind, "en": en, "ko": ko or en, "x": round(point[0], 3), "y": round(point[1], 3), "k": min_k}
    if ele:
        item["e"] = ele
    labels.append(item)


def merge_lines(lines):
    """Join touching lines; linemerge refuses a union that is already one line."""
    union = unary_union(lines)
    return linemerge(union) if isinstance(union, MultiLineString) else union


def osm_rivers(cache, labels):
    """Korean rivers from OpenStreetMap, merged by name; returns {min_k: geometries}."""
    q = f'[out:json][timeout:170];way["waterway"="river"]["name"](33.0,124.0,43.2,131.2);out tags geom;'
    ways = defaultdict(list)
    names = {}
    for e in overpass(cache, "osm_rivers", q):
        t = e["tags"]
        key = t.get("name:ko") or t["name"]
        ways[key].append(LineString([(p["lon"], p["lat"]) for p in e["geometry"]]))
        names.setdefault(key, {"en": t.get("name:en")})
        names[key]["en"] = names[key]["en"] or t.get("name:en")
    out = defaultdict(list)
    for key, lines in ways.items():
        merged = merge_lines(lines)
        for part in getattr(merged, "geoms", [merged]):
            km = km_len(part)
            if km < 25:
                continue
            min_k = 12 if km >= 150 else 35 if km >= 60 else 90
            out[min_k].append(part.simplify(0.002 if km >= 60 else 0.001))
            en = OSM_RIVER_EN.get(key) or names[key]["en"]
            en = re.sub(r"\s*\(.*?\)", "", en) if en else None
            ko = key if re.search("[가-힣]", key) else None
            if km >= 60 and (en or ko):
                add_label(labels, "river", en or "", ko, part.interpolate(0.5, normalized=True).coords[0],
                          30 if km >= 150 else 70)
    return out


def osm_lakes(cache, labels):
    """Korean lakes and reservoirs from OpenStreetMap; returns {min_k: geometries}."""
    q = ('[out:json][timeout:170];(way["natural"="water"]["water"~"^(lake|reservoir|lagoon)$"]["name"]'
         '(33.0,124.0,43.2,131.2);relation["natural"="water"]["water"~"^(lake|reservoir|lagoon)$"]["name"]'
         '(33.0,124.0,43.2,131.2););out tags geom;')
    out = defaultdict(list)
    for e in overpass(cache, "osm_lakes", q):
        t = e["tags"]
        if e["type"] == "way":
            if len(e["geometry"]) < 4:
                continue
            polys = [Polygon([(p["lon"], p["lat"]) for p in e["geometry"]])]
        else:
            parts = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in e.get("members", [])
                     if m.get("role") == "outer" and len(m.get("geometry", [])) > 1]
            polys = list(polygonize([merge_lines(parts)])) if parts else []
        for poly in polys:
            poly = make_valid(poly)
            km2 = km2_area(poly) if not poly.is_empty else 0
            if km2 < 0.7:
                continue
            min_k = 12 if km2 >= 20 else 50 if km2 >= 4 else 130
            out[min_k].append(poly.simplify(0.0008))
            ko = t.get("name:ko") or (t["name"] if re.search("[가-힣]", t["name"]) else None)
            if km2 >= 8 and (t.get("name:en") or ko):
                p = poly.representative_point()
                add_label(labels, "lake", t.get("name:en") or "", ko, (p.x, p.y), 40 if km2 >= 20 else 90)
    return out


def natural_earth_water(cache, labels):
    """Rivers and lakes outside Korea; returns ({min_k: rivers}, {min_k: lakes})."""
    rivers, lakes = defaultdict(list), defaultdict(list)
    labelled = set()
    for p, g in natural_earth(cache, "ne_10m_rivers_lake_centerlines"):
        rank, inside = p.get("scalerank") or 10, g.intersects(REGION)
        if rank > (9 if inside else 5):
            continue
        g = g.difference(KOREA)
        if g.is_empty:
            continue
        min_k = 1 if rank <= 3 else 3 if rank <= 6 else 6
        rivers[min_k].append(g.simplify(0.01))
        name = p.get("name_en") or p.get("name")
        if name and rank <= 7 and name not in labelled and inside:
            labelled.add(name)
            line = max(getattr(g, "geoms", [g]), key=lambda s: s.length)
            add_label(labels, "river", name, RIVER_KO.get(name), line.interpolate(0.5, normalized=True).coords[0],
                      3 if rank <= 3 else 9)
    for p, g in natural_earth(cache, "ne_10m_lakes"):
        rank, inside = p.get("scalerank") or 10, g.intersects(REGION)
        if rank > (9 if inside else 5):
            continue
        g = g.difference(KOREA)
        if g.is_empty:
            continue
        lakes[1 if rank <= 3 else 3 if rank <= 6 else 6].append(g.simplify(0.005))
        if p.get("name") and rank <= 7 and inside:
            c = g.representative_point()
            add_label(labels, "lake", p["name"], p.get("name_ko"), (c.x, c.y), 4 if rank <= 4 else 10)
    return rivers, lakes


def relief_names(cache, labels):
    """Peaks, mountain ranges and seas."""
    for p, g in natural_earth(cache, "ne_10m_geography_regions_elevation_points"):
        if p.get("featurecla") != "mountain" or not p.get("name"):
            continue
        rank, inside = p.get("scalerank") or 10, g.intersects(REGION)
        in_korea = g.intersects(KOREA)
        if not in_korea and rank > (7 if inside else 4):
            continue
        en, ko = PEAK_FIX.get(p["name"], (p["name"], p.get("name_ko")))
        add_label(labels, "peak", en, ko, (g.x, g.y), 12 if in_korea else 3 if rank <= 4 else 8, p.get("elevation"))
    for en, ko, lon, lat, ele in EXTRA_PEAKS:
        add_label(labels, "peak", en, ko, (lon, lat), 40, ele)
    for en, ko, lon, lat in RANGES:
        add_label(labels, "range", en, ko, (lon, lat), 22)
    for p, g in natural_earth(cache, "ne_10m_geography_regions_polys"):
        if p.get("featurecla") not in ("Range/mtn", "Plateau", "Desert", "Plain") or p.get("scalerank", 9) > 4:
            continue
        c = g.representative_point()
        add_label(labels, "range", p.get("name_en") or p["name"], p.get("name_ko"), (c.x, c.y),
                  1.5 if p["scalerank"] <= 2 else 3)
    for p, g in natural_earth(cache, "ne_10m_geography_marine_polys"):
        if not p.get("name") or p.get("featurecla") not in ("sea", "bay", "gulf", "ocean", "strait"):
            continue
        rank, inside = p.get("scalerank") or 9, g.intersects(REGION)
        if rank > (5 if inside else 2):
            continue
        c = g.representative_point()
        en = "East Sea / Sea of Japan" if p["name"] == "Sea of Japan" else p["name"]
        add_label(labels, "sea", en, p.get("name_ko"), (c.x, c.y), 0 if rank <= 1 else 2 if rank <= 2 else 8)


def tile_range(z, lon0, lat0, lon1, lat1):
    """Slippy-map tile indices covering a lon/lat box."""
    n = 2 ** z

    def ty(lat):
        return (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return (int((lon0 + 180) / 360 * n), min(n - 1, int((lon1 + 180) / 360 * n)),
            int(ty(lat1)), min(n - 1, int(ty(lat0))))


def elevation(cache, z, x0, x1, y0, y1):
    """Stitch Terrarium tiles into one elevation grid in metres."""
    folder = cache / "terrain"
    folder.mkdir(exist_ok=True)

    def one(xy):
        x, y = xy
        path = fetch(TILE_URL.format(z=z, x=x, y=y), folder / f"{z}_{x}_{y}.png")
        a = np.asarray(Image.open(io.BytesIO(path.read_bytes())).convert("RGB"), dtype=np.float32)
        return xy, a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768

    grid = np.zeros(((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256), dtype=np.float32)
    with ThreadPoolExecutor(16) as pool:
        for (x, y), a in pool.map(one, [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]):
            grid[(y - y0) * 256:(y - y0 + 1) * 256, (x - x0) * 256:(x - x0 + 1) * 256] = a
    return grid


def relief_image(elev, z, y0, exaggeration):
    """Colour elevation by height and shade it from the north-west; the sea stays transparent."""
    n = 256 * 2 ** z
    rows = np.arange(elev.shape[0]) + y0 * 256 + 0.5
    lat = np.arctan(np.sinh(np.pi * (1 - 2 * rows / n)))
    metres = 40075016 * np.cos(lat) / n                  # ground size of one pixel on each row
    dy, dx = np.gradient(elev)
    dx = dx / metres[:, None] * exaggeration
    dy = dy / metres[:, None] * exaggeration
    az, alt = math.radians(315), math.radians(45)
    shade = (math.sin(alt) + math.cos(alt) * (-dx * math.sin(az) + dy * math.cos(az))) / np.sqrt(1 + dx ** 2 + dy ** 2)
    shade = np.clip(shade / math.sin(alt), 0.35, 1.3)    # 1 = flat ground

    stops = [s[0] for s in TINT]
    land = np.clip(elev, 0, None)
    rgb = np.stack([np.interp(land, stops, [s[1][i] for s in TINT]) for i in range(3)], axis=-1) * shade[..., None]
    alpha = np.interp(land, stops, [s[2] for s in TINT])
    alpha = np.maximum(alpha, np.clip(np.abs(shade - 1) * 1.6, 0, 0.75))     # relief also shows on low ground
    alpha[elev <= 0] = 0
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8), "RGBA")


def build_relief(cache):
    """Write one relief image per zoom level; returns their placement in map units (the world is 1000 wide)."""
    levels = []
    for z, lon0, lat0, lon1, lat1, exaggeration, min_k in RELIEF:
        x0, x1, y0, y1 = tile_range(z, lon0, lat0, lon1, lat1)
        image = relief_image(elevation(cache, z, x0, x1, y0, y1), z, y0, exaggeration)
        name = f"relief_z{z}.webp"
        image.save(OUT / name, quality=72, alpha_quality=80, method=6)
        unit = 1000 / 2 ** z
        levels.append({"src": f"geo/{name}", "k": min_k, "x": x0 * unit, "y": y0 * unit,
                       "w": (x1 - x0 + 1) * unit, "h": (y1 - y0 + 1) * unit})
        print(name, image.size, (OUT / name).stat().st_size // 1024, "KB")
    return levels


def by_zoom(groups):
    """{min_k: geometries} -> [{k, r: rings}], coarse layers first."""
    return [{"k": k, "r": [r for g in groups[k] for r in rings(g) if len(r) >= 4]} for k in sorted(groups)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True, help="folder for downloaded source data")
    cache = ap.parse_args().cache
    cache.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(exist_ok=True)

    labels = []
    land = unary_union([g for _, g in natural_earth(cache, "ne_10m_land")]).intersection(REGION)
    coast = [g.intersection(REGION) for _, g in natural_earth(cache, "ne_10m_coastline")]
    borders = [g.intersection(REGION) for _, g in natural_earth(cache, "ne_10m_admin_0_boundary_lines_land")]
    rivers, lakes = natural_earth_water(cache, labels)
    for k, g in osm_rivers(cache, labels).items():
        rivers[k] += g
    for k, g in osm_lakes(cache, labels).items():
        lakes[k] += g
    relief_names(cache, labels)

    layers = {
        "region": list(REGION.bounds),
        "land": rings(land.simplify(0.004)),
        "coast": [r for g in coast for r in rings(g.simplify(0.004)) if len(r) >= 4],
        "borders": [r for g in borders for r in rings(g.simplify(0.004)) if len(r) >= 4],
        "rivers": by_zoom(rivers),
        "lakes": by_zoom(lakes),
        "labels": labels,
        "relief": build_relief(cache),
    }
    text = "// Generated by data/build_map_layers.py: do not edit.\nconst MAP_LAYERS = " \
           + json.dumps(layers, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (OUT / "map_layers.js").write_text(text, encoding="utf-8")
    print("map_layers.js", len(text.encode()) // 1024, "KB,", len(labels), "labels")


if __name__ == "__main__":
    main()
