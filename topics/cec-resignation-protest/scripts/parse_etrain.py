"""Parse saved etrain.info train pages into per-coach and per-train seat capacity tables."""
import csv, html, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
run = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else sorted(p for p in (ROOT / "data/raw/etrain").iterdir() if p.is_dir())[-1]

cap = {r["type_key"]: int(r["capacity"]) for r in csv.DictReader(open(ROOT / "data/curated/coach_capacity.csv"))}
trains = list(csv.DictReader(open(ROOT / "data/curated/cancelled_trains.csv")))

COACH = re.compile(r'<div\s+(?:etitle="([^"]*)"\s+)?class="rake ([^"]*)" rake="([^"]*)"></div><span>([^<]*)</span>')
ROW = re.compile(r'<div class="pdl5">(\d+)</div><small><div class="pdl5">([A-Z]+)</div></small>.*?'
                 r'<div class="fixwelps">([^<]*)</div>.*?(\d+) kms.*?<td class="txt-lt dborder">(.*?)</td>', re.S)
NON_PASSENGER = {"rake-eng", "rake-pwr", "rake-pc"}
GENERAL = {"rake-gen", "rake-grd"}

rake_rows, train_rows = [], []
for t in trains:
    no = t["train_no"]
    page = (run / "trains" / f"{no}.html").read_text(encoding="utf-8", errors="replace")
    coaches = COACH.findall(page)
    counted = uncounted_gen = unknown = 0
    seats = 0
    for pos, (etitle, cls, key, label) in enumerate(coaches, 1):
        title = html.unescape(etitle).split("<")[0]
        kind = cls.replace("rake ", "")
        c = cap.get(key) if key else None
        if c is not None:
            counted += 1
            seats += c
        elif kind in GENERAL:
            uncounted_gen += 1
        elif kind not in NON_PASSENGER:
            unknown += 1
        rake_rows.append({"train_no": no, "position": pos, "label": label, "type_key": key, "etrain_title": title,
                          "css_kind": kind, "capacity": "" if c is None else c})
    # Read the scheduled arrival at the destination listed in the curated table.
    arrival = ""
    for seq, code, name, km, times in ROW.findall(page):
        if code == t["dest_code"]:
            arrival = re.sub(r"<[^>]+>", " ", times).split()
            arrival = " ".join(arrival[:3])
    train_rows.append({
        "train_no": no, "train_name": t["train_name"], "origin_name": t["origin_name"], "dest_code": t["dest_code"],
        "category": t["category"], "rake_listed_on_etrain": bool(coaches),
        "reserved_capacity_full": seats if coaches else "", "coaches_counted": counted,
        "uncounted_general_coaches": uncounted_gen, "unclassified_coaches": unknown,
        "etrain_sched_arrival_at_dest": arrival, "etrain_page": f"{run.relative_to(ROOT)}/trains/{no}.html"})

out = ROOT / "data/processed"
for name, rows in (("train_rakes.csv", rake_rows), ("train_capacity.csv", train_rows)):
    with open(out / name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

cancelled = [r for r in train_rows if r["category"].startswith("cancelled") and r["reserved_capacity_full"] != ""]
print(f"source run: {run.relative_to(ROOT)}")
print(f"trains with rake: {sum(r['rake_listed_on_etrain'] for r in train_rows)}/{len(train_rows)}; "
      f"cancelled with rake: {len(cancelled)}; reserved seats (cancelled, incl. Tilak Bridge): "
      f"{sum(r['reserved_capacity_full'] for r in cancelled):,}; uncounted general coaches: "
      f"{sum(r['uncounted_general_coaches'] for r in cancelled)}; unclassified: {sum(r['unclassified_coaches'] for r in cancelled)}")
