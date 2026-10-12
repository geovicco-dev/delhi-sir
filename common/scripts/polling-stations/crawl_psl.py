"""Crawl CEO Delhi's current polling station list for all 70 ACs and save one row per part."""

import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://ceodelhinet.nic.in/ceodelhiweb/PSL.aspx"
AC_SEL = "#ctl00_ContentPlaceHolder1_DropDownListDistNO"
GRID = "#ctl00_ContentPlaceHolder1_GridViewEroll"
OUT = Path("raw/psl")
COLS = ["dist_no", "dist_name", "ac_no", "ac_name", "part_no", "locality", "polling_area", "address"]


def ac_options(page):
    return page.eval_on_selector(
        AC_SEL,
        "s => [...s.options].map(o => [o.value, o.textContent.trim()]).filter(o => o[0] && o[0] !== '0')",
    )


def choose(page, value, pause):
    with page.expect_navigation(wait_until="networkidle", timeout=120000):
        page.select_option(AC_SEL, value=value)
    time.sleep(pause)


def grid(page):
    """Return the header row and data rows of the results grid as cell text."""
    if not page.query_selector(GRID):
        return [], []
    rows = page.eval_on_selector(
        GRID,
        """g => [...g.querySelectorAll('tr')].map(tr =>
              [...tr.querySelectorAll('th,td')].map(c => c.innerText.replace(/\\s+/g, ' ').trim()))""",
    )
    # Drop the empty footer row by keeping only rows that carry a part number.
    return rows[0], [r for r in rows[1:] if len(r) == len(COLS) and r[4].isdigit()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--acs", nargs="*", type=int, help="AC numbers to crawl (default: all)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between requests")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    rows_out, headers, manifest = [], {}, []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle")
        time.sleep(args.delay)
        for value, label in ac_options(page):
            ac_no = int(value)
            if args.acs and ac_no not in args.acs:
                continue
            choose(page, value, args.delay)
            fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            html = page.content()
            (OUT / f"AC{ac_no:03d}.html").write_text(html, encoding="utf-8")
            header, rows = grid(page)
            headers[ac_no] = header
            for r in rows:
                rows_out.append({**dict(zip(COLS, r)), "fetched_at": fetched_at})
            grid_html = page.eval_on_selector(GRID, "g => g.outerHTML") if rows else ""
            manifest.append({"ac_no": ac_no, "ac_label": label, "rows": len(rows),
                             "sha1": hashlib.sha1(grid_html.encode()).hexdigest() if rows else "",
                             "fetched_at": fetched_at})
            print(f"AC {ac_no:>2} {label}: {len(rows)} parts", flush=True)
        browser.close()

    with open(OUT / "psl_tables.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[*COLS, "fetched_at"])
        w.writeheader()
        w.writerows(rows_out)
    with open(OUT / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ac_no", "ac_label", "rows", "sha1", "fetched_at"])
        w.writeheader()
        w.writerows(manifest)
    (OUT / "psl_headers.json").write_text(json.dumps(headers, indent=1, ensure_ascii=False))
    print(f"Wrote {len(rows_out)} parts from {len(manifest)} ACs to {OUT / 'psl_tables.csv'}")


if __name__ == "__main__":
    main()
