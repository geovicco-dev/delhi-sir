"""Give every current part a point location by matching 2017 polling stations or geocoding."""

import argparse
import json
import re
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
from rapidfuzz import fuzz

NOMINATIM = "https://nominatim.openstreetmap.org/search"


def norm(s):
    s = str(s or "").upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\bEXTN?\b|\bEXTENSION\b", "EXT", s)
    s = re.sub(r"\b(II|2ND)\b", "2", s)
    s = re.sub(r"\b(I|1ST)\b", "1", s)
    s = re.sub(r"\bIII\b", "3", s)
    return re.sub(r"\s+", " ", s).strip()


def compact(s):
    """Return a spacing-insensitive form of a name, so 'SARAI KALE KHAN' equals 'SARAIKALE KHAN'."""
    return norm(s).replace(" ", "")


def score(query, candidate):
    a, b = norm(query), norm(candidate)
    if not a or not b:
        return 0
    return max(fuzz.token_set_ratio(a, b), fuzz.ratio(compact(a), compact(b)))


def load_sites(ref_path):
    ref = pd.read_csv(ref_path)
    ref = ref.dropna(subset=["lat", "lon", "ac_no", "part_no"])
    ref["ac_no"] = ref.ac_no.astype(int)
    ref["key"] = ref.lat.round(5).astype(str) + "," + ref.lon.round(5).astype(str)
    sites = (ref.groupby(["ac_no", "key"])
             .agg(lat=("lat", "first"), lon=("lon", "first"),
                  localities=("ps_locality", lambda x: sorted(set(map(str, x)))),
                  n_2017_parts=("part_no", "size"),
                  parts_2017=("part_no", lambda x: sorted(int(v) for v in x)))
             .reset_index())
    sites["site_id"] = "S" + sites.index.astype(str).str.zfill(5)
    return sites


def match_2017(parts, sites, min_score, band=5):
    """Match each part to the best 2017 site in its AC, breaking near-ties by part-number position."""
    out = []
    by_ac = {ac: g for ac, g in sites.groupby("ac_no")}
    max_now = parts.groupby("ac_no").part_no.max()
    for _, p in parts.iterrows():
        query = " ".join(str(p.get(c, "") or "") for c in ("building", "locality", "part_name"))
        g = by_ac.get(int(p.ac_no))
        if g is None:
            out.append(dict(ref_site="", ref_score=0))
            continue
        scores = [max(score(query, loc) for loc in locs) for locs in g.localities]
        top = max(scores)
        if top < min_score:
            out.append(dict(ref_site="", ref_score=round(top)))
            continue
        max_2017 = max(max(x) for x in g.parts_2017)
        rel = p.part_no / max_now[p.ac_no] * max_2017
        cands = [(abs(min(abs(n - rel) for n in pl)), i)
                 for i, (sc, pl) in enumerate(zip(scores, g.parts_2017)) if sc >= top - band]
        out.append(dict(ref_site=g.iloc[min(cands)[1]].site_id, ref_score=round(top)))
    return pd.DataFrame(out, index=parts.index)


def build_locations(parts, sites):
    """Build one row per polling location, placed at the 2017 site most of its parts matched."""
    site_xy = sites.set_index("site_id")[["lat", "lon"]]
    rows = []
    for (ac, loc_key), g in parts.groupby(["ac_no", "loc_key"], sort=False):
        votes = g[g.ref_site != ""].groupby("ref_site").ref_score.agg(["size", "max"])
        row = dict(ac_no=ac, loc_key=loc_key, building=g.building.iloc[0], locality=g.locality.iloc[0],
                   part_name=g.sort_values("part_no").part_name.iloc[0], first_part=g.part_no.min(),
                   lat=None, lon=None, method="", score=int(g.ref_score.max()))
        if len(votes):
            best = votes.sort_values(["size", "max"], ascending=False).index[0]
            row.update(lat=site_xy.at[best, "lat"], lon=site_xy.at[best, "lon"], method="psleci_2017",
                       score=int(votes.at[best, "max"]))
        rows.append(row)
    locs = pd.DataFrame(rows).sort_values(["ac_no", "first_part"]).reset_index(drop=True)
    locs["site_id"] = [f"AC{a:03d}-L{i + 1:03d}" for a, i in zip(locs.ac_no, locs.groupby("ac_no").cumcount())]
    return locs


def geocode_missing(locs, acs, cache_path, email):
    import requests
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    bounds = acs.set_index("AC_NO").geometry.bounds
    todo = locs[locs.lat.isna()]
    print(f"Geocoding {len(todo)} locations (cached answers are reused)", flush=True)
    for n, (i, loc) in enumerate(todo.iterrows(), start=1):
        b = bounds.loc[int(loc.ac_no)]
        queries = [("nominatim_building", ", ".join(x for x in (loc.building, loc.locality) if x)),
                   ("nominatim_locality", loc.locality),
                   ("nominatim_part_name", loc.part_name)]
        for method, text in queries:
            if not text:
                continue
            q = f"{text}, Delhi"
            key = f"{q}|{int(loc.ac_no)}"
            if key not in cache:
                r = requests.get(NOMINATIM, timeout=30,
                                 params=dict(q=q, format="json", limit=1, bounded=1,
                                             viewbox=f"{b.minx},{b.maxy},{b.maxx},{b.miny}"),
                                 headers={"User-Agent": f"delhi-sir-research ({email})"})
                r.raise_for_status()
                cache[key] = r.json()
                cache_path.write_text(json.dumps(cache))
                time.sleep(1.1)
            if cache[key]:
                locs.loc[i, ["lat", "lon"]] = float(cache[key][0]["lat"]), float(cache[key][0]["lon"])
                locs.loc[i, "method"] = method
                break
        if n % 50 == 0:
            print(f"  {n}/{len(todo)}", flush=True)
    return locs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", default="raw/notices_pdfs/manifest.csv")
    ap.add_argument("--ref", default="data/polling-stations/eci-2017/delhi_polling_stations_2017_psleci.csv")
    ap.add_argument("--acs", default="data/boundaries/delhi_ac_uncollectable.geojson")
    ap.add_argument("--out", default="data/polling-stations")
    ap.add_argument("--min-score", type=int, default=85)
    ap.add_argument("--geocode", action="store_true")
    ap.add_argument("--email", default="you@example.com", help="contact for the Nominatim User-Agent")
    args = ap.parse_args()

    parts = pd.read_csv(args.parts, dtype=str).fillna("")
    parts = parts[parts.part_no.str.isdigit()].drop_duplicates(["ac_no", "part_no"]).copy()
    parts["ac_no"] = parts.ac_no.astype(int)
    parts["part_no"] = parts.part_no.astype(int)
    for c in ("building", "locality", "polling_area"):
        if c not in parts:
            parts[c] = ""
    # Group parts by building and locality, giving parts with no building their own location.
    parts["loc_key"] = parts.building.str.upper() + "|" + parts.locality.str.upper()
    parts.loc[parts.building == "", "loc_key"] = "P" + parts.part_no.astype(str)

    sites = load_sites(args.ref)
    parts = parts.join(match_2017(parts, sites, args.min_score))
    locs = build_locations(parts, sites)

    acs = gpd.read_file(args.acs)
    acs["AC_NO"] = acs.AC_NO.astype(int)
    if args.geocode:
        locs = geocode_missing(locs, acs, Path("raw/geocode_cache.json"), args.email)

    # Check whether each point falls inside its own AC, with a 500 m allowance.
    located = locs.dropna(subset=["lat"])
    pts = gpd.GeoDataFrame(located, geometry=gpd.points_from_xy(located.lon, located.lat), crs=4326).to_crs(32643)
    polys = acs.to_crs(32643).set_index("AC_NO").geometry.buffer(500)
    locs["in_ac"] = pd.Series([polys.loc[a].contains(g) for a, g in zip(pts.ac_no, pts.geometry)], index=pts.index)

    parts = parts.merge(locs[["ac_no", "loc_key", "lat", "lon", "method", "score", "site_id", "in_ac"]],
                        on=["ac_no", "loc_key"])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cols = ["ac_no", "part_no", "part_name", "lat", "lon", "method", "score", "site_id", "in_ac"]
    parts.sort_values(["ac_no", "part_no"])[cols].to_csv(out / "parts_located.csv", index=False)

    feats = []
    for loc in locs.dropna(subset=["lat"]).itertuples():
        g = parts[parts.site_id == loc.site_id]
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(loc.lon, 6), round(loc.lat, 6)]},
                      "properties": {"ac_no": int(loc.ac_no), "site_id": loc.site_id, "building": loc.building,
                                     "locality": loc.locality, "parts": sorted(g.part_no.tolist()),
                                     "n_parts": len(g), "names": sorted(set(g.part_name)),
                                     "method": loc.method, "score": int(loc.score), "in_ac": bool(loc.in_ac)}})
    (out / "polling_sites.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

    n, nl = len(parts), len(locs)
    print(f"{n} parts at {nl} polling locations")
    by_part = parts.method.replace("", "unlocated").value_counts()
    by_loc = locs.method.replace("", "unlocated").value_counts()
    for k in by_loc.index:
        print(f"  {k:20s} {by_loc[k]:5d} locations ({by_loc[k] / nl:.0%})  {by_part[k]:6d} parts ({by_part[k] / n:.0%})")
    outside = locs[locs.in_ac.eq(False)]
    print(f"  outside own AC (+500 m): {len(outside)} locations, {int(parts.in_ac.eq(False).sum())} parts; "
          f"by method: {outside.method.value_counts().to_dict()}")
    shared = located.groupby(["lat", "lon"]).size()
    print(f"  located locations sharing a point with another location: {int(shared[shared > 1].sum())}")
    print(f"Wrote {out / 'parts_located.csv'} and {out / 'polling_sites.geojson'} ({len(feats)} sites)")


if __name__ == "__main__":
    main()
