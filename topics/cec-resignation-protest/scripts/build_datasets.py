"""Build the map-ready train, metro and terminal layers from the raw and curated data."""
import csv, json, math, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW, CUR, OUT = ROOT / "data/raw", ROOT / "data/curated", ROOT / "data/processed"
OUT.mkdir(parents=True, exist_ok=True)

JANTAR_MANTAR = (77.2166, 28.6271)  # Lon, lat.

stations = {f["properties"]["code"]: f for f in json.load(open(RAW / "datameet/stations.json"))["features"] if f["geometry"]}


def coord(code):
    return tuple(stations[code]["geometry"]["coordinates"])


def km(a, b):
    lo1, la1, lo2, la2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def fc(features):
    return {"type": "FeatureCollection", "features": features}


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False))


# Build one schematic line per cancelled train.
trains = []
for r in csv.DictReader(open(CUR / "cancelled_trains.csv")):
    o, d = coord(r["coord_code"]), coord(r["dest_code"])
    props = {k: v for k, v in r.items()}
    props["source_count"] = int(r["source_count"])
    props["distance_km_straight"] = round(km(o, d))
    trains.append({"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": [list(o), list(d)]}})
dump("cancelled_trains.geojson", fc(trains))

# Build the metro lines and stations, leaving out RRTS.
rels = [r for r in json.load(open(RAW / "osm/delhi_metro_routes.json"))["elements"] if "RRTS" not in r["tags"].get("name", "")]
names = {e["id"]: e["tags"].get("name:en", e["tags"].get("name", "")) for e in json.load(open(RAW / "osm/delhi_metro_stop_tags.json"))["elements"]}

stops, ways, stop_lines = {}, {}, {}
for r in rels:
    line = r["tags"].get("name", "").split(" (")[0].split(":")[0].strip()
    for m in r["members"]:
        if m["type"] == "node" and m["role"].startswith("stop") and "lat" in m:
            stops[m["ref"]] = (m["lon"], m["lat"])
            stop_lines.setdefault(m["ref"], set()).add(line)
        elif m["type"] == "way" and m["role"] in ("", "route", "forward", "backward") and "geometry" in m:
            ways.setdefault(m["ref"], {"coords": [[g["lon"], g["lat"]] for g in m["geometry"]], "lines": set()})["lines"].add(line)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


# Map list spellings to OSM spellings where they differ.
ALIASES = {
    "jasola": ["jasolaviharshaheenbagh"], "barakhambaroad": ["barakhambharoad"], "chawribazar": ["chawribazaar"],
    "jafrabad": ["jaffrabad"], "ina": ["dillihaatina"], "rkashrammarg": ["ramakrishnaashrammarg"],
    "sevateerthudyogbhawan": ["sevateerth"], "saraikalekhannizamuddin": ["saraikalekhannizamuddin"],
    "maujpur": ["maujpurbabarpur"],
}


def match(listed):
    keys = ALIASES.get(norm(listed), [norm(listed)])
    for exact in (True, False):
        hits = [sid for sid, nm in names.items() if sid in stops and any((norm(nm) == k) if exact else norm(nm).startswith(k) for k in keys)]
        if hits:
            return hits
    return []


closed, unmatched = {}, []
for r in csv.DictReader(open(CUR / "metro_closures_requested.csv")):
    hits = match(r["name_as_listed"])
    if not hits:
        unmatched.append(r["name_as_listed"])
    for sid in hits:
        closed[sid] = r

dump("metro_lines.geojson", fc([
    {"type": "Feature", "properties": {"osm_way_id": wid, "lines": sorted(w["lines"])}, "geometry": {"type": "LineString", "coordinates": w["coords"]}}
    for wid, w in ways.items()]))
dump("metro_stations.geojson", fc([
    {"type": "Feature",
     "properties": {"osm_node_id": sid, "name": names.get(sid, ""), "lines": sorted(stop_lines[sid]),
                    "gates_shut_requested": sid in closed,
                    "name_as_listed": closed[sid]["name_as_listed"] if sid in closed else None,
                    "km_to_jantar_mantar": round(km(xy, JANTAR_MANTAR), 2)},
     "geometry": {"type": "Point", "coordinates": list(xy)}}
    for sid, xy in stops.items()]))

# Build the Delhi rail terminals table.
TERMINALS = [("NDLS", "arrivals_cancelled_04-14"), ("NZM", "arrivals_cancelled_04-14"), ("TKJ", "some_trains_cancelled"),
             ("DLI", "normal"), ("ANVT", "normal"), ("DEE", "normal"), ("DEC", "normal")]
with open(OUT / "delhi_rail_terminals.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["code", "name", "lon", "lat", "status_10oct", "km_to_jantar_mantar", "nearest_metro", "nearest_metro_km", "nearest_metro_gates_shut"])
    for code, status in TERMINALS:
        p = coord(code)
        d, sid = min((km(p, xy), sid) for sid, xy in stops.items())
        w.writerow([code, stations[code]["properties"]["name"], *p, status, round(km(p, JANTAR_MANTAR), 1), names.get(sid, ""), round(d, 2), sid in closed])

print(f"trains: {len(trains)} | metro ways: {len(ways)} | stops: {len(stops)} | closed stop nodes: {len(closed)} "
      f"({len({r['name_as_listed'] for r in closed.values()})}/57 names) | unmatched: {unmatched}")
