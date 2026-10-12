"""Extract DMRC's network data from its journey-planner bundle and flag the requested closures."""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data/raw/dmrc/map_bundle"
OUT = ROOT / "data/processed/dmrc_network.json"

# Map web register names to the current names on the Aug 2026 DMRC poster.
CURRENT_NAME = {
    "Rohini West": "Dr. Baba Saheb Ambedkar Hospital",
    "Rohini East": "Rohini",
    "Udyog Bhawan": "Seva Teerth",
    "Mayur Vihar Pocket-1": "Shri Ram Mandir Mayur Vihar",
}
# Map police-letter spellings to register spellings where they differ.
LIST_ALIAS = {
    "Seva Teerth (Udyog Bhawan)": "Udyog Bhawan",
    "R.K. Ashram Marg": "Ramakrishna Ashram Marg",
    "INA": "Dilli Haat-INA",
    "Jasola": "Jasola Vihar Shaheen Bagh",  # Magenta Line by list order; Jasola Apollo is on the Violet Line.
    "GTB Nagar": "Guru Teg Bahadur Nagar",
    "Maujpur": "Maujpur-Babarpur",
    "Rohini East": "Rohini East",
    "Rohini West": "Rohini West",
}


def module(js_text, mid):
    m = re.search(rf"{mid}:function\(\w\)\{{\w\.exports=JSON\.parse\('(.*?)'\)\}}", js_text, re.S)
    if not m:
        raise SystemExit(f"webpack module {mid} not found: DMRC may have redeployed; see R6 in PROVENANCE.md")
    return json.loads(bytes(m.group(1), "utf-8").decode("unicode_escape"))


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main():
    reg = module(next(BUNDLE.glob("chunk_1.*.js")).read_text(), 259)
    pos = module(next(BUNDLE.glob("chunk_10.*.js")).read_text(), 2259)
    lines, stations = [], {}
    for key, line in reg.items():
        pts = pos[key]
        assert len(pts) == len(line["stations"]), key
        lines.append({"key": key, "name": line["name"], "colour": line["color"], "stations": [s["code"] for s in line["stations"]]})
        for s, p in zip(line["stations"], pts):
            name = s["name"].strip()
            st = stations.setdefault(s["code"], {"name_dmrc_web": name, "name_current": CURRENT_NAME.get(name, name),
                                                 "name_hi": s["name_hi"], "x": p["x"], "y": p["y"],
                                                 "interchange": False, "lines": [], "gates_shut_requested": False,
                                                 "name_as_listed": None})
            st["interchange"] |= bool(p.get("interchange"))
            if line["name"] not in st["lines"]:
                st["lines"].append(line["name"])
    by_name = {norm(v["name_dmrc_web"]): k for k, v in stations.items()}
    unmatched = []
    for r in csv.DictReader(open(ROOT / "data/curated/metro_closures_requested.csv")):
        listed = r["name_as_listed"]
        code = by_name.get(norm(LIST_ALIAS.get(listed, listed)))
        if code is None:
            unmatched.append(listed)
            continue
        stations[code]["gates_shut_requested"] = True
        stations[code]["name_as_listed"] = listed
    OUT.write_text(json.dumps({"source": "DMRC journey planner bundle, modules 259 + 2259 (R6)", "lines": lines,
                               "stations": stations}, ensure_ascii=False, indent=1))
    n = sum(v["gates_shut_requested"] for v in stations.values())
    print(f"{len(lines)} lines, {len(stations)} stations, {n} flagged closed, unmatched: {unmatched}")


if __name__ == "__main__":
    main()
