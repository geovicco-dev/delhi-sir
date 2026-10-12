"""Build the Delhi-wide rail, metro, boundary and Jantar Mantar layers for the QGIS project."""
import csv, json, math, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OSM, OUT = ROOT / "data/raw/osm", ROOT / "data/processed"
OUT.mkdir(parents=True, exist_ok=True)

JANTAR_MANTAR = (77.2166, 28.6271)  # Lon, lat, the same point build_datasets.py measures from.

# Map OSM colour names that are not hex codes to hex.
NAMED_COLOURS = {"aqua": "#00B5C9", "gray": "#808080", "grey": "#808080"}


def fc(features):
    return {"type": "FeatureCollection", "features": features}


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False))


def line_geom(way):
    return {"type": "LineString", "coordinates": [[g["lon"], g["lat"]] for g in way["geometry"]]}


ways = json.load(open(OSM / "delhi_rail_ways.json"))["elements"]

# Classify national rail ways and write the railway lines layer.
def rail_class(t):
    label = f'{t.get("name", "")} {t.get("operator", "")}'
    if "RRTS" in label or "NCRTC" in label or "National Capital Region Transport" in label:
        return "rrts"
    if "Freight Corridor" in label or "DFCCIL" in label:
        return "freight_corridor"
    if t["railway"] == "narrow_gauge":
        return "heritage"
    return "service" if t.get("service") else "main"


def is_metro(t):
    # Treat subway-tagged RRTS track as national rail, not metro.
    return t["railway"] == "subway" and rail_class(t) != "rrts"


rail = []
for w in ways:
    t = w["tags"]
    if is_metro(t):
        continue
    rail.append({"type": "Feature", "geometry": line_geom(w), "properties": {
        "osm_way_id": w["id"], "class": rail_class(t), "railway": t["railway"], "service": t.get("service"),
        "usage": t.get("usage"), "name": t.get("name"), "operator": t.get("operator"), "electrified": t.get("electrified")}})
dump("railway_lines.geojson", fc(rail))

# Map each metro way id to its line and colour from the route relations, skipping RRTS.
way_line = {}
for r in json.load(open(OSM / "delhi_metro_routes.json"))["elements"]:
    if "RRTS" in r["tags"].get("name", ""):
        continue
    line = re.split(r" \(|:", r["tags"].get("name", ""))[0].strip()
    colour = r["tags"].get("colour", "")
    colour = NAMED_COLOURS.get(colour.lower(), colour.upper())
    for m in r["members"]:
        if m["type"] == "way":
            way_line.setdefault(m["ref"], (line, colour))
line_colour = dict(way_line.values())


def line_from_name(name):
    """Return the metro line named in a way's name tag, or None."""
    for line in line_colour:
        if line.split()[0].lower() in (name or "").lower().split():
            return line
    return None


metro = []
for w in ways:
    t = w["tags"]
    if not is_metro(t):
        continue
    line, colour = way_line.get(w["id"], (None, None))
    source = "route_relation" if line else None
    if not line and (line := line_from_name(t.get("name"))):
        colour, source = line_colour[line], "way_name"
    metro.append({"type": "Feature", "geometry": line_geom(w), "properties": {
        "osm_way_id": w["id"], "line": line or "Unassigned", "colour": colour or "#9A9A9A", "line_source": source,
        "service": t.get("service"), "is_depot_or_siding": bool(t.get("service")), "name": t.get("name")}})
dump("metro_tracks.geojson", fc(metro))

# Write the under-construction and proposed lines layer.
def planned_mode(t):
    kind = t.get("construction") or t.get("proposed") or ""
    if "RRTS" in t.get("name", ""):
        return "rrts"
    return "metro" if kind == "subway" else "rail"


planned = []
for w in json.load(open(OSM / "delhi_rail_planned.json"))["elements"]:
    t = w["tags"]
    if (t.get("construction") or t.get("proposed")) == "station":  # Skip depot buildings, which are not track.
        continue
    planned.append({"type": "Feature", "geometry": line_geom(w), "properties": {
        "osm_way_id": w["id"], "status": t["railway"], "mode": planned_mode(t), "name": t.get("name"),
        "operator": t.get("operator")}})
dump("planned_lines.geojson", fc(planned))

# Write the rail stations layer, leaving out metro stations.
def station_class(t):
    label = f'{t.get("operator", "")} {t.get("network", "")} {t.get("name", "")}'
    if "RapidX" in label or "RRTS" in label or "NCRTC" in label or "National Capital Region T" in label:
        return "rrts"
    if "DFCCIL" in label:
        return "freight_corridor"
    return "indian_railways"


stations = []
for e in json.load(open(OSM / "delhi_rail_stations.json"))["elements"]:
    t = e["tags"]
    name = t.get("name:en") or t.get("name")
    if t.get("station") == "subway" or t.get("subway") == "yes" or not name:
        continue
    lon, lat = (e["lon"], e["lat"]) if e["type"] == "node" else (e["center"]["lon"], e["center"]["lat"])
    stations.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {
        "osm_id": f'{e["type"]}/{e["id"]}', "name": name, "code": t.get("ref"), "railway": t["railway"],
        "class": station_class(t), "operator": t.get("operator")}})
dump("rail_stations.geojson", fc(stations))

# Join the DMRC station register to OSM stop positions.
DMRC_LINE_TO_OSM = {"Orange Line": "Airport Express Line", "Gurgoan": "Rapid MetroRail Gurgaon"}
# Map DMRC codes to OSM stop names where normalising the spelling is not enough.
DMRC_ALIASES = {
    "RJNM": "Rajendra Nagar",  # Now named Major Mohit Sharma Rajendra Nagar.
    "NBAA": "Shaheed Sthal",
    "GTBR": "GTB Nagar",
    "CWBR": "Chawri Bazaar",
    "DW": "Dwarka - Kakrola",  # Blue and Grey interchange; OSM uses the newer name.
    "BRKR": "Barakhambha Road",
    "GEC": "Noida Golf Course",
    "CIPK": "Brigadier Hoshiyar Singh",
    "MIAA": "Mundka Industrial Area",
    "SMSM": "Surajmal Stadium",
    "JLNS": "Jawaharlal Nehru Stadium",
    "TKDS": "Tughlakabad",
    "BAPB": "Badarpur",
    "BKMR": "Badhkal Mor",
    "ECMJ": "Escorts Mujesar",
    "BVHM": "Raja Nahar Singh",
    "SOEN": "South Extension",
    "MVPO": "Shree Ram Mandir Mayur Vihar",
    "JFRB": "Jaffrabad",
    "SNVH": "Nanaksar - Sonia Vihar",
    "JPVE": "Jagatpur - Wazirabad",
    "IIT": "IIT Delhi",
    "NPPR": "North Pitampura - Prashant Vihar",  # OSM has one station where DMRC lists NPPR and PHVR.
    "APOT": "IGI Airport",
    "DL2": "DLF Phase 2", "DL3": "Phase 3 Station", "PH1": "DLF Phase 1",
    "MAL": "Moulsari Avenue Station",
}

# Add OSM stops that share a DMRC code, such as the Airport Express terminal under NDI.
DMRC_EXTRA_STOPS = {"NDI": "New Delhi Airport Express Terminal"}


def station_key(name):
    s = (name or "").lower()
    s = re.sub(r"\((?:[a-z]+ line)\)", "", s)  # Drops a line suffix such as "(Yellow Line)".
    s = re.sub(r"\b(?:metro )?station$", "", s.strip())  # Drops a trailing "Metro Station".
    s = re.sub(r"\bsec(?:tor)?[- ]*(\d+)", r"sector \1", s)  # Normalises "Sec-15" and "Sector-34" to "sector N".
    s = re.sub(r"^sector (\d+) noida$", r"noida sector \1", s.strip())  # Rewrites "sector N noida" as "noida sector N".
    s = re.sub(r"\bi\.?s\.?b\.?t\.?$", "", s)  # Drops a trailing "I.S.B.T".
    s = re.sub(r"-1$", " i", s)  # Rewrites "-1" as " i".
    return re.sub(r"[^a-z0-9]", "", s)


def km(a, b):
    lo1, la1, lo2, la2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


osm_stops = json.load(open(OUT / "metro_stations.geojson"))["features"]
# Load the 45 stations DMRC shut, as OSM stop names.
shut_dmrc = {n.strip() for r in csv.DictReader(open(ROOT / "data/curated/metro_closures_2026-10-10_dmrc.csv"))
             if r["in_revised_45"] == "True" for n in r["osm_names"].split(";")}
dmrc = json.load(open(OUT / "dmrc_network.json"))
join_rows, dmrc_points, used = [], [], set()
for code, st in dmrc["stations"].items():
    lines = {DMRC_LINE_TO_OSM.get(l, l) for l in st["lines"]}
    on_line = [f for f in osm_stops if lines & set(f["properties"]["lines"])]
    hits, method = [], None
    for how, wanted in (("exact", {st["name_current"], st["name_dmrc_web"]}), ("alias", {DMRC_ALIASES.get(code)})):
        keys = {station_key(w) for w in wanted if w}
        hits = [f for f in on_line if station_key(f["properties"]["name"]) in keys]
        if hits:
            method = how if how == "alias" or any(f["properties"]["name"] in wanted for f in hits) else "normalised"
            break
    if code in DMRC_EXTRA_STOPS:
        hits += [f for f in osm_stops if f["properties"]["name"] == DMRC_EXTRA_STOPS[code]]
    osm_names = sorted({f["properties"]["name"] for f in hits})
    join_rows.append({"dmrc_code": code, "dmrc_name": st["name_current"], "dmrc_lines": "; ".join(st["lines"]),
                      "match": method or "unmatched", "osm_names": "; ".join(osm_names), "osm_stop_nodes": len(hits)})
    if not hits:
        continue
    used.update(f["properties"]["osm_node_id"] for f in hits)
    xy = [sum(f["geometry"]["coordinates"][i] for f in hits) / len(hits) for i in (0, 1)]
    spread = max(km(xy, f["geometry"]["coordinates"]) for f in hits)
    closed = st["gates_shut_requested"]
    dmrc_points.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": xy}, "properties": {
        "source": "DMRC register + OSM position", "dmrc_code": code, "name": st["name_current"], "name_dmrc_web": st["name_dmrc_web"], "name_hi": st["name_hi"],
        "lines": "; ".join(st["lines"]), "interchange": st["interchange"], "gates_shut_requested": closed,
        "closure_label": "Gates shut: requested by Delhi Police" if closed else None,
        "gates_shut_dmrc": bool(shut_dmrc & set(osm_names)),
        "name_as_listed": st["name_as_listed"], "osm_stop_names": "; ".join(osm_names),
        "osm_stop_node_ids": "; ".join(str(f["properties"]["osm_node_id"]) for f in hits), "match": method,
        "position_spread_km": round(spread, 2), "km_to_jantar_mantar": round(km(xy, JANTAR_MANTAR), 2)}})
# Keep a point without DMRC fields for OSM stations missing from the DMRC register.
for name in sorted({f["properties"]["name"] for f in osm_stops if f["properties"]["osm_node_id"] not in used}):
    stops = [f for f in osm_stops if f["properties"]["name"] == name]
    lines = sorted({l for f in stops for l in f["properties"]["lines"]})
    xy = [sum(f["geometry"]["coordinates"][i] for f in stops) / len(stops) for i in (0, 1)]
    dmrc_points.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": xy}, "properties": {
        "source": "OSM only (not in DMRC register)", "dmrc_code": None, "name": name, "name_dmrc_web": None,
        "name_hi": None, "lines": "; ".join(lines), "interchange": None, "gates_shut_requested": False,
        "closure_label": None, "gates_shut_dmrc": name in shut_dmrc, "name_as_listed": None, "osm_stop_names": name,
        "osm_stop_node_ids": "; ".join(str(f["properties"]["osm_node_id"]) for f in stops), "match": "osm_only",
        "position_spread_km": round(max(km(xy, f["geometry"]["coordinates"]) for f in stops), 2),
        "km_to_jantar_mantar": round(km(xy, JANTAR_MANTAR), 2)}})
    join_rows.append({"dmrc_code": "", "dmrc_name": "", "dmrc_lines": "", "match": "osm_only",
                      "osm_names": name, "osm_stop_nodes": len(stops), "osm_lines": "; ".join(lines)})
dump("metro_stations_dmrc.geojson", fc(dmrc_points))
with open(OUT / "metro_station_join.csv", "w", newline="") as f:
    w = csv.DictWriter(f, ["dmrc_code", "dmrc_name", "dmrc_lines", "match", "osm_names", "osm_stop_nodes", "osm_lines"])
    w.writeheader()
    w.writerows(join_rows)

# Write the Delhi boundary and Jantar Mantar layers.
(OUT / "delhi_boundary.geojson").unlink(missing_ok=True)  # Delete first because the GeoJSON driver cannot overwrite.
subprocess.run(["ogr2ogr", "-f", "GeoJSON", "-select", "name", str(OUT / "delhi_boundary.geojson"), str(OSM / "delhi_nct_boundary.osm"), "multipolygons"], check=True)
dump("jantar_mantar.geojson", fc([{"type": "Feature", "geometry": {"type": "Point", "coordinates": list(JANTAR_MANTAR)},
                                   "properties": {"name": "Jantar Mantar", "role": "protest site, 10 Oct 2026"}}]))

assigned = sum(f["properties"]["line"] != "Unassigned" for f in metro if not f["properties"]["is_depot_or_siding"])
mainline = sum(not f["properties"]["is_depot_or_siding"] for f in metro)
unmatched = [r["dmrc_code"] for r in join_rows if r["match"] == "unmatched"]
near_open = [p["properties"]["name"] for p in dmrc_points
             if p["properties"]["km_to_jantar_mantar"] <= 3.7 and not p["properties"]["gates_shut_requested"]]
print(f"station points: {len(dmrc_points)} | DMRC stations placed: {sum(p['properties']['dmrc_code'] is not None for p in dmrc_points)}/{len(dmrc['stations'])} | unmatched: {unmatched} | "
      f"closed placed: {sum(p['properties']['gates_shut_requested'] for p in dmrc_points)}/57 requested, "
      f"{sum(p['properties']['gates_shut_dmrc'] for p in dmrc_points)}/45 shut by DMRC "
      f"({sum(p['properties']['gates_shut_dmrc'] and p['properties']['km_to_jantar_mantar'] <= 3.7 for p in dmrc_points)} within 3.7 km) | "
      f"open within 3.7 km of Jantar Mantar: {near_open or 'none'}")
print(f"rail ways: {len(rail)} | rail stations: {len(stations)} | planned ways: {len(planned)} | metro ways: {len(metro)} "
      f"(mainline {mainline}, with a line {assigned})")
