"""Download the part-wise ASDD PDFs from ECI, skipping parts already downloaded or missing."""

import argparse
import csv
import hashlib
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ECI_PDF = "https://voters.eci.gov.in/eroll/asd/2026/u05/{ac}/uncollectable_elector_report_ac{ac}_part{part}_ENG.pdf"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
PARTS = Path("raw/psl/psl_tables.csv")
OUT = Path("raw/asdd_pdfs")  # Git-ignored because the PDFs contain names and EPIC numbers.
MANIFEST = OUT / "manifest.csv"
FIELDS = ["district", "ac_no", "ac_name", "part_no", "part_name", "url", "file",
          "bytes", "sha1", "fetched_at", "status"]
FINISHED = ("ok", "http 404")
MAX_FAILURES_IN_A_ROW = 5


def fetch(url, retries=3):
    status = ""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
                content_type = resp.headers.get("Content-Type")
            if body[:4] == b"%PDF":
                return body, "ok"
            status = f"not a pdf, {content_type}"
        except urllib.error.HTTPError as e:
            status = f"http {e.code}"
            if 400 <= e.code < 500:
                break  # Missing file or refused client; retrying will not help.
        except Exception as e:  # Network error.
            status = f"error {e}"
        time.sleep(5 * attempt)
    return None, status


def load_done():
    done = set()
    if MANIFEST.exists():
        with open(MANIFEST, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["status"] in FINISHED:
                    done.add((r["ac_no"], r["part_no"]))
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--acs", nargs="*", help="AC numbers to crawl (default: all)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between requests")
    args = ap.parse_args()
    wanted = {str(int(a)) for a in args.acs} if args.acs else None

    with open(PARTS, encoding="utf-8") as f:
        parts = [p for p in csv.DictReader(f) if not wanted or p["ac_no"] in wanted]
    parts.sort(key=lambda p: (int(p["ac_no"]), int(p["part_no"])))
    done = load_done()
    todo = [p for p in parts if (p["ac_no"], p["part_no"]) not in done]
    print(f"{len(parts)} parts listed, {len(todo)} to fetch", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    new_file = not MANIFEST.exists()
    mf = open(MANIFEST, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(mf, fieldnames=FIELDS)
    if new_file:
        w.writeheader()

    failures, failed_parts, last_ac = 0, 0, None
    for p in todo:
        ac, part = p["ac_no"], p["part_no"]
        if ac != last_ac:
            print(f"{p['dist_no']} - {p['dist_name']} / {ac} - {p['ac_name']}", flush=True)
            last_ac = ac
        url = ECI_PDF.format(ac=ac, part=part)
        body, status = fetch(url)
        # Record only finished parts in the manifest so refusals and errors are retried next run.
        if status in FINISHED:
            dest = OUT / f"AC{int(ac):03d}" / f"AC{int(ac):03d}_P{int(part):04d}.pdf"
            if body:
                dest.parent.mkdir(exist_ok=True)
                dest.write_bytes(body)
            w.writerow({
                "district": f"{p['dist_no']} - {p['dist_name']}", "ac_no": ac, "ac_name": p["ac_name"],
                "part_no": part, "part_name": p["locality"], "url": url,
                "file": str(dest) if body else "", "bytes": len(body) if body else 0,
                "sha1": hashlib.sha1(body).hexdigest() if body else "",
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": status,
            })
            mf.flush()
        if status != "ok":
            print(f"   ! part {part}: {status}", flush=True)
        # Count refusals and network errors in a row, and stop once ECI or the connection looks down.
        failures = 0 if status in FINISHED else failures + 1
        failed_parts += status not in FINISHED
        if failures >= MAX_FAILURES_IN_A_ROW:
            mf.close()
            sys.exit(f"Stopping: {failures} failures in a row (last: {status}). "
                     "Check the connection to voters.eci.gov.in, then re-run.")
        time.sleep(args.delay + random.uniform(0, 1))
    mf.close()
    if failed_parts:
        # Exit non-zero so the background service retries the failed parts later.
        sys.exit(f"Done, but {failed_parts} parts failed this run; re-run to retry them.")
    print("Done. Every listed part is downloaded or confirmed missing.")


if __name__ == "__main__":
    main()
