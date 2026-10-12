"""Map each current part to its pre-renumbering parts and flag parts that one BLO covers."""

import sys
from pathlib import Path

import duckdb

# Require this many ASDD records before trusting that a part came from a single old part.
MIN_RECORDS = 30


def main(asdd_csv="processed/asdd.csv", out_dir="data/polling-stations"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"""create temp table pairs as
        select ac_no::int as ac_no, part_no::int as part_no, old_part_no::int as old_part_no, count(*) as asdd_records
        from read_csv('{asdd_csv}', header=true, delim=',', quote='"', escape='"', all_varchar=true)
        group by all""")
    path = out / "part_map.csv"
    con.execute(f"""copy (
        select p.ac_no, p.part_no, p.old_part_no, p.asdd_records,
               count(*) over w as old_parts_in_part,
               sum(p.asdd_records) over w as asdd_records_in_part,
               (count(*) over w = 1 and sum(p.asdd_records) over w >= {MIN_RECORDS}) as one_blo
        from pairs p
        window w as (partition by p.ac_no, p.part_no)
        order by p.ac_no, p.part_no, p.old_part_no
    ) to '{path}' (header, delimiter ',')""")
    s = con.execute(f"""select count(*), count(distinct (ac_no, part_no)), count(distinct (ac_no, old_part_no)),
                               count(distinct (ac_no, part_no)) filter (where one_blo)
                        from read_csv('{path}')""").fetchone()
    assert s is not None
    print(f"{s[0]:,} pairs -> {path}; {s[1]:,} current parts, {s[2]:,} old parts, {s[3]:,} with one BLO")


if __name__ == "__main__":
    main(*sys.argv[1:])
