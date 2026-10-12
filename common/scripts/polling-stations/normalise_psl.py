"""Turn the crawled polling station list into one clean row per current part."""

import argparse
import re
from pathlib import Path

import pandas as pd

CITY_OR_PIN = re.compile(r"^(NEW )?DELHI\b[\s\-.,0-9]*$|^\d{6}$", re.I)
SECTION = re.compile(r", (?=\d+ - )")


def clean(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return re.sub(r"(\s*,)+", ",", s).strip(" ,")


def split_address(address):
    pieces = [p.strip() for p in clean(address).split(",") if p.strip()]
    building, rest = (pieces[0], pieces[1:]) if pieces else ("", [])
    locality = []
    for p in rest:
        if not CITY_OR_PIN.match(p) and p.upper() not in (x.upper() for x in locality):
            locality.append(p)
    return building, ", ".join(locality)


def polling_area(text, part_name):
    entries = []
    for e in SECTION.split(clean(text)):
        m = re.match(r"^(\d+) - (.*)$", e)
        if not m:
            continue
        section = m.group(2).strip()
        if part_name and section.upper().endswith(part_name.upper()):
            head = section[: -len(part_name)]
            if head and head[-1] not in " ,-":
                section = f"{head}, {section[-len(part_name):]}"
        entries.append((int(m.group(1)), section))
    return "; ".join(s for _, s in sorted(entries))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--psl", default="raw/psl/psl_tables.csv")
    ap.add_argument("--notices", default="raw/notices_pdfs/manifest.csv")
    ap.add_argument("--out", default="raw/psl/parts_current.csv")
    args = ap.parse_args()

    psl = pd.read_csv(args.psl, dtype=str).fillna("")
    rows = []
    for r in psl.itertuples():
        part_name = clean(r.locality)
        building, locality = split_address(r.address)
        rows.append({"ac_no": int(r.ac_no), "part_no": int(r.part_no), "part_name": part_name,
                     "building": building, "locality": locality,
                     "polling_area": polling_area(r.polling_area, part_name)})
    parts = pd.DataFrame(rows).sort_values(["ac_no", "part_no"])
    parts.to_csv(args.out, index=False)
    print(f"Wrote {len(parts)} parts in {parts.ac_no.nunique()} ACs to {args.out}")

    dups = parts.duplicated(["ac_no", "part_no"]).sum()
    gaps = [ac for ac, g in parts.groupby("ac_no") if sorted(g.part_no) != list(range(1, len(g) + 1))]
    print(f"  duplicate parts: {dups}; ACs with gaps in part numbering: {gaps or 'none'}")
    print(f"  empty building: {(parts.building == '').sum()}, empty locality: {(parts.locality == '').sum()}")

    if not Path(args.notices).exists():
        print(f"  no notices manifest at {args.notices}; skipped the cross-check")
        return
    notices = pd.read_csv(args.notices, dtype=str).fillna("")
    notices = notices[notices.part_no.str.isdigit()].drop_duplicates(["ac_no", "part_no"])
    notices["ac_no"] = notices.ac_no.astype(int)
    notices["part_no"] = notices.part_no.astype(int)
    crawled = sorted(notices.ac_no.unique())
    here = parts[parts.ac_no.isin(crawled)]
    count = (here.groupby("ac_no").size().rename("psl")
             .to_frame().join(notices.groupby("ac_no").size().rename("notices")))
    bad = count[count.psl != count.notices]
    j = here.merge(notices[["ac_no", "part_no", "part_name"]], on=["ac_no", "part_no"],
                   how="outer", suffixes=("", "_notices"), indicator=True)
    renamed = j[(j._merge == "both") & (j.part_name.str.upper() != j.part_name_notices.str.strip().str.upper())]
    print(f"  notices manifest covers {len(crawled)} of 70 ACs ({len(notices)} parts)")
    print(f"  AC part-count mismatches: {len(bad)}" + (f"\n{bad.to_string()}" if len(bad) else ""))
    print(f"  parts only in PSL: {(j._merge == 'left_only').sum()}, only in notices: {(j._merge == 'right_only').sum()}, "
          f"name differs: {len(renamed)}")


if __name__ == "__main__":
    main()
