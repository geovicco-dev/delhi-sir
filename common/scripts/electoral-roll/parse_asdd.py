"""Parse the part-wise ASDD PDFs into one CSV row per elector."""

import argparse
import csv
import hashlib
import os
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pdfplumber

HEADER_AC = re.compile(r"AC/PC No and Name:\s*(\d+)\s*-\s*(.+)")
HEADER_PART = re.compile(r"Part No and Name:\s*(\d+)\s*-\s*(.+)")
FILE_NAME = re.compile(r"AC(\d+)_P(\d+)\.pdf$")
# Match the start of a record line: S.No, then the first characters of a possibly wrapped EPIC.
RECORD_START = re.compile(r"^(\d+) [A-Za-z]{2,4}[/\d]", re.M)
EPIC = re.compile(r"[A-Z]{3}\d{7}|[A-Z]{2}/\d{2}/\d{3}/\d{6,7}")
FIELDS = ["ac_no", "ac_name", "part_no", "part_name", "s_no", "epic", "name",
          "relation_type", "relation_name", "old_part_no", "old_part_serial", "age",
          "gender", "reason", "source_file", "source_sha1"]


def clean(cell):
    return re.sub(r"\s+", " ", (cell or "").replace("\n", " ")).strip()


def parse_pdf(path):
    """Return the rows and problems for one PDF, never quoting personal details in problems."""
    path = Path(path)
    sha1 = hashlib.sha1(path.read_bytes()).hexdigest()
    rows, problems, text_snos = [], [], []
    with pdfplumber.open(path) as pdf:
        first = pdf.pages[0].extract_text() or ""
        m_ac, m_part = HEADER_AC.search(first), HEADER_PART.search(first)
        ac_no, ac_name = (m_ac.group(1), m_ac.group(2).strip()) if m_ac else ("", "")
        part_no, part_name = (m_part.group(1), m_part.group(2).strip()) if m_part else ("", "")
        for page in pdf.pages:
            text_snos += [int(s) for s in RECORD_START.findall(page.extract_text() or "")]
            for table in page.extract_tables():
                for r in table:
                    r = [clean(c) for c in r]
                    if len(r) < 10 or not r[0].isdigit():
                        continue  # Header row or stray line.
                    rows.append({
                        "ac_no": ac_no, "ac_name": ac_name, "part_no": part_no, "part_name": part_name,
                        "s_no": r[0], "epic": r[1].replace(" ", ""), "name": r[2], "relation_type": r[3],
                        "relation_name": r[4], "old_part_no": r[5], "old_part_serial": r[6],
                        "age": r[7], "gender": r[8], "reason": r[9],
                        "source_file": path.name, "source_sha1": sha1,
                    })
    m_file = FILE_NAME.search(path.name)
    if m_file and (str(int(m_file.group(1))), str(int(m_file.group(2)))) != (ac_no, part_no):
        problems.append(f"header says AC {ac_no or '?'} part {part_no or '?'}")
    if not rows:
        problems.append("no rows")
    if [int(x["s_no"]) for x in rows] != list(range(1, len(rows) + 1)):
        problems.append("S.No sequence has gaps")
    if sorted(text_snos) != [int(x["s_no"]) for x in rows]:
        problems.append(f"{len(rows)} table rows but {len(text_snos)} records in the text")
    return rows, problems


def safe_parse(path):
    try:
        return parse_pdf(path)
    except Exception as e:  # Corrupt file or an HTML error page saved as .pdf.
        return [], [f"error: {str(e).splitlines()[0]}"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="folder of ASDD PDFs, searched recursively")
    ap.add_argument("out", help="CSV to write")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    args = ap.parse_args()

    pdfs = sorted(Path(args.src).rglob("*.pdf"))
    total, unusual, problems = 0, 0, []
    with open(args.out, "w", newline="", encoding="utf-8") as f, \
            ProcessPoolExecutor(args.workers) as pool:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        # Write rows in input order so the CSV is sorted by AC and part.
        for path, (rows, issues) in zip(pdfs, pool.map(safe_parse, pdfs, chunksize=8)):
            w.writerows(rows)
            total += len(rows)
            unusual += sum(not EPIC.fullmatch(r["epic"]) for r in rows)
            problems += [(path.name, issue) for issue in issues]
    print(f"{len(pdfs)} PDFs, {total} rows -> {args.out}")
    print(f"  EPICs kept as printed but not in a known format: {unusual}")
    for name, issue in problems:
        print("  !", name, issue)


if __name__ == "__main__":
    main()
