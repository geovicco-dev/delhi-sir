"""Parse the part-wise SIR 2026 notice PDFs into one CSV row per elector."""

import argparse
import csv
import hashlib
import os
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pdfplumber

HEADER_AC = re.compile(r"AC No and Name:\s*(\d+)\s*-\s*(.+)")
HEADER_PART = re.compile(r"Part No and Name:\s*(\d+)\s*-\s*(.+)")
FILE_NAME = re.compile(r"AC(\d+)_P(\d+)\.pdf$")
FIELDS = ["ac_no", "ac_name", "part_no", "part_name", "s_no", "part_serial",
          "epic", "name", "age", "gender", "reason", "source_file", "source_sha1"]


def clean(cell):
    return re.sub(r"\s+", " ", (cell or "").replace("\n", " ")).strip()


def parse_pdf(path):
    """Return the rows and problems for one PDF, never quoting personal details in problems."""
    path = Path(path)
    sha1 = hashlib.sha1(path.read_bytes()).hexdigest()
    rows, problems = [], []
    with pdfplumber.open(path) as pdf:
        first = pdf.pages[0].extract_text() or ""
        m_ac, m_part = HEADER_AC.search(first), HEADER_PART.search(first)
        ac_no, ac_name = (m_ac.group(1), m_ac.group(2).strip()) if m_ac else ("", "")
        part_no, part_name = (m_part.group(1), m_part.group(2).strip()) if m_part else ("", "")
        for page in pdf.pages:
            for table in page.extract_tables():
                for r in table:
                    r = [clean(c) for c in r]
                    if len(r) < 7 or not r[0].isdigit():
                        continue  # Header row or stray line.
                    rows.append({
                        "ac_no": ac_no, "ac_name": ac_name,
                        "part_no": part_no, "part_name": part_name,
                        # Join an EPIC back together where it wraps inside its cell.
                        "s_no": r[0], "part_serial": r[1], "epic": r[2].replace(" ", ""),
                        "name": r[3], "age": r[4], "gender": r[5], "reason": r[6],
                        "source_file": path.name, "source_sha1": sha1,
                    })
    m_file = FILE_NAME.search(path.name)
    if m_file and (str(int(m_file.group(1))), str(int(m_file.group(2)))) != (ac_no, part_no):
        problems.append(f"header says AC {ac_no or '?'} part {part_no or '?'}")
    if not rows:
        # Record parts that publish a no-notices placeholder instead of a list.
        problems.append("no rows (placeholder?) " + first[:80].replace("\n", " "))
    if [int(x["s_no"]) for x in rows] != list(range(1, len(rows) + 1)):
        problems.append("S.No sequence has gaps")
    return rows, problems


def safe_parse(path):
    try:
        return parse_pdf(path)
    except Exception as e:  # Corrupt file or an HTML error page saved as .pdf.
        return [], [f"error: {str(e).splitlines()[0]}"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="folder of notice PDFs, searched recursively")
    ap.add_argument("out", help="CSV to write")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    args = ap.parse_args()

    pdfs = sorted(Path(args.src).rglob("*.pdf"))
    total, problems = 0, []
    with open(args.out, "w", newline="", encoding="utf-8") as f, \
            ProcessPoolExecutor(args.workers) as pool:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        # Write rows in input order so the CSV is sorted by AC and part.
        for path, (rows, issues) in zip(pdfs, pool.map(safe_parse, pdfs, chunksize=8)):
            w.writerows(rows)
            total += len(rows)
            problems += [(path.name, issue) for issue in issues]
    print(f"{len(pdfs)} PDFs, {total} rows -> {args.out}")
    for name, issue in problems:
        print("  !", name, issue)


if __name__ == "__main__":
    main()
