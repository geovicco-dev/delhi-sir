"""Count ASDD electors per current part, per AC and per old part from the person-level table."""

import hashlib
import sys
from pathlib import Path

import pandas as pd

# Map each reason as printed in the PDFs to its column name.
REASONS = {
    "Permanently Shifted": "reason_shifted",
    "Untraceable/Absent": "reason_absent",
    "Death": "reason_dead",
    "Already enrolled": "reason_duplicate",
}
# Define age bands in years at the time of the list; 18-19 are first-time electors.
AGE_BANDS = [(18, 19), (20, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 79), (80, None)]
AGE_COLS = [f"age_{lo}_{hi}" if hi else f"age_{lo}_plus" for lo, hi in AGE_BANDS]
COUNTS = ["asdd_total", *REASONS.values(),
          "asdd_male", "asdd_female", "asdd_third_gender", *AGE_COLS]
OLD_PART_CSV = "processed/asdd_by_old_part.csv"


def electors(asdd_csv):
    cols = ["ac_no", "part_no", "old_part_no", "age", "gender", "reason", "source_sha1"]
    df = pd.read_csv(asdd_csv, dtype=str, keep_default_na=False, usecols=cols)
    unknown = sorted(set(df["reason"]) - REASONS.keys())
    if unknown:
        # Stop on an unknown reason so it cannot silently drop out of the counts.
        sys.exit(f"Unknown reason text, add it to REASONS: {unknown}")
    df["asdd_total"] = 1
    for text, col in REASONS.items():
        df[col] = df["reason"].eq(text).astype(int)
    df["asdd_male"] = df["gender"].eq("M").astype(int)
    df["asdd_female"] = df["gender"].eq("F").astype(int)
    df["asdd_third_gender"] = df["gender"].eq("O").astype(int)
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    for (lo, hi), col in zip(AGE_BANDS, AGE_COLS):
        df[col] = (df["age"] >= lo) & (df["age"] <= hi if hi else True)
        df[col] = df[col].astype(int)
    return df


def parts(manifest_csv):
    m = pd.read_csv(manifest_csv, dtype=str, keep_default_na=False)
    m = m[m["status"] == "ok"].drop_duplicates(["ac_no", "part_no"], keep="last")
    m["crawl_date"] = m["fetched_at"].str[:10]
    return m[["ac_no", "ac_name", "part_no", "part_name", "crawl_date", "sha1"]].rename(
        columns={"sha1": "source_sha1"})


def date_span(dates):
    lo, hi = min(dates), max(dates)
    return lo if lo == hi else f"{lo}/{hi}"


def by_int(*cols):
    return lambda s: s.astype(int) if s.name in cols else s


def by_part(people, part_list):
    hashes = people.drop_duplicates(["ac_no", "part_no"])[["ac_no", "part_no", "source_sha1"]]
    stale = hashes.merge(part_list, on=["ac_no", "part_no"])
    if (stale["source_sha1_x"] != stale["source_sha1_y"]).any():
        sys.exit("processed/asdd.csv does not match the PDFs in the manifest; re-run the parser.")
    g = people.groupby(["ac_no", "part_no"])
    out = (part_list.join(g[COUNTS].sum(), on=["ac_no", "part_no"])
           .join(g["age"].median().rename("median_age"), on=["ac_no", "part_no"])
           .join(g["old_part_no"].nunique().rename("old_parts"), on=["ac_no", "part_no"]))
    out[[*COUNTS, "old_parts"]] = out[[*COUNTS, "old_parts"]].fillna(0).astype(int)
    out = out.sort_values(["ac_no", "part_no"], key=by_int("ac_no", "part_no"))
    return out[["ac_no", "ac_name", "part_no", "part_name", *COUNTS, "median_age", "old_parts",
                "crawl_date", "source_sha1"]]


def by_ac(people, part_rows):
    g = part_rows.groupby(["ac_no", "ac_name"])
    out = g[COUNTS].sum()
    out.insert(0, "parts", g.size())
    out.insert(1, "old_parts", people.groupby("ac_no")["old_part_no"].nunique()
               .reindex(out.index.get_level_values("ac_no")).fillna(0).astype(int).values)
    out["median_age"] = people.groupby("ac_no")["age"].median().reindex(out.index.get_level_values("ac_no")).values
    out["crawl_date"] = g["crawl_date"].agg(date_span)
    # Fingerprint the AC with a sha1 of its part hashes, one per line, in part order.
    out["source_sha1"] = g["source_sha1"].agg(lambda s: hashlib.sha1("\n".join(s).encode()).hexdigest())
    return out.reset_index().sort_values("ac_no", key=lambda s: s.astype(int))


def by_old_part(people):
    g = people.groupby(["ac_no", "old_part_no"])
    out = g[COUNTS].sum()
    out["median_age"] = g["age"].median()
    out["current_parts"] = g["part_no"].nunique()
    out = out.reset_index().sort_values(["ac_no", "old_part_no"], key=by_int("ac_no", "old_part_no"))
    return out[["ac_no", "old_part_no", *COUNTS, "median_age", "current_parts"]]


README = """# ASDD aggregates

Counts of electors named in the SIR 2026 ASDD lists (Absent, Shifted, Dead, Duplicate):
electors on the pre-SIR roll whose enumeration form was not collected, and who are not in
the draft roll of 31 Aug 2026. Built from the part-wise PDFs that the CEO Delhi ASDD page
(https://ceodelhi.gov.in/ceodelhiasdd/) opens on voters.eci.gov.in. Unofficial; not
affiliated with CEO Delhi or the Election Commission of India.

Crawl date: {crawl_dates}. Coverage: {n_parts:,} current parts in {n_acs} assembly
constituencies, {n_asdd:,} electors. The per-AC totals equal CEO Delhi's 31 Aug 2026
uncollectable-form counts (data/electoral-roll/ac_uncollectable_31aug2026.csv).

Generated by `scripts/electoral-roll/aggregate_asdd.py`. No names, EPIC numbers or other person-level
fields are stored here.

## asdd_by_part.csv

One row per current part (polling station), using the new part numbers (14,947 parts
after rationalisation). These join to notices_by_part.csv on ac_no and part_no.

| Column | Meaning |
|---|---|
| ac_no, ac_name | Assembly constituency |
| part_no, part_name | Current part number and name |
| asdd_total | Electors named in the part's ASDD list |
| reason_* | Electors with that reason (see below). Each elector has one reason, so these add up to asdd_total |
| asdd_male, asdd_female, asdd_third_gender | Electors printed as male (M), female (F) and third gender (O). They add up to asdd_total |
| age_18_19 ... age_80_plus | Electors in each age band: 18-19, 20-29, 30-39, 40-49, 50-59, 60-69, 70-79, 80 and over. They add up to asdd_total |
| median_age | Median age of the electors named |
| old_parts | Number of old parts (the {n_old:,} before rationalisation) these electors were listed in |
| crawl_date | Date (UTC) the part's PDF was downloaded |
| source_sha1 | SHA-1 of the downloaded PDF, to detect republished lists |

| Column | Reason text in the PDF |
|---|---|
{reason_rows}

## asdd_by_ac.csv

The same counts summed to each constituency, plus `parts` (current parts) and `old_parts`.
median_age is the median over all electors in the AC, not a sum. crawl_date is one date,
or a `first/last` range when the AC's parts were downloaded across more than one day.
source_sha1 is the SHA-1 of the AC's part hashes joined with newlines in part order.

Every count is shown as counted, including small ones.
"""


def main(asdd_csv="processed/asdd.csv", manifest_csv="raw/asdd_pdfs/manifest.csv",
         out_dir="data/electoral-roll"):
    people = electors(asdd_csv)
    part_rows = by_part(people, parts(manifest_csv))
    ac_rows = by_ac(people, part_rows)
    old_rows = by_old_part(people)
    n_asdd = int(part_rows["asdd_total"].sum())
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    part_rows.to_csv(out / "asdd_by_part.csv", index=False)
    ac_rows.to_csv(out / "asdd_by_ac.csv", index=False)
    old_rows.to_csv(OLD_PART_CSV, index=False)
    (out / "README_asdd.md").write_text(README.format(
        crawl_dates=date_span(part_rows["crawl_date"]).replace("/", " to "),
        n_parts=len(part_rows), n_old=len(old_rows), n_acs=len(ac_rows), n_asdd=n_asdd,
        reason_rows="\n".join(f"| {col} | {text} |" for text, col in REASONS.items()),
    ), encoding="utf-8")
    print(f"{len(part_rows)} parts, {len(ac_rows)} ACs, {n_asdd} electors -> {out}/ "
          f"(old parts: {OLD_PART_CSV})")


if __name__ == "__main__":
    main(*sys.argv[1:])
