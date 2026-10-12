"""Crawl CEO Delhi's List of BLO page for all 70 ACs and save one row per part."""

import argparse
import csv
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://ceodelhinet.nic.in/ceodelhiweb/BloUpdateDetails.aspx"
AC_SEL = "#ctl00_ContentPlaceHolder1_ddlACNO"
GRID = "#ctl00_ContentPlaceHolder1_gvBloUpdateSearchPage"
OUT = Path("raw/blo")
COLS = ["ac_no", "part_no", "blo_name", "designation", "mobile"]
MANIFEST_COLS = ["ac_no", "ac_label", "page", "rows", "sha1", "fetched_at"]

# Read the grid rows, the current page number and the link to the next page.
READ_GRID = """g => {
    const rows = [...g.rows].map(tr => [...tr.cells].map(c => c.innerText.replace(/\\s+/g, ' ').trim()));
    const data = rows.slice(1).filter(r => r.length === 5 && /^\\d+$/.test(r[1]));
    const last = g.rows[g.rows.length - 1];
    let current = 1, next = null;
    g.querySelectorAll('[data-next]').forEach(e => e.removeAttribute('data-next'));
    if (last.cells.length !== 5) {
        const items = [...last.querySelectorAll('a, span')].filter(e => !e.querySelector('a, span'));
        const i = items.findIndex(e => e.tagName === 'SPAN');
        if (i >= 0) current = parseInt(items[i].innerText.trim(), 10);
        if (i >= 0 && items[i + 1] && items[i + 1].tagName === 'A') {
            items[i + 1].setAttribute('data-next', '1');
            next = items[i + 1].innerText.trim();
        }
    }
    return {data, current, next, html: g.outerHTML};
}"""


class CrawlError(Exception):
    pass


def ac_options(page):
    return page.eval_on_selector(
        AC_SEL,
        "s => [...s.options].map(o => [o.value, o.textContent.trim()]).filter(o => /^\\d+$/.test(o[0]))",
    )


def postback(page, action, pause):
    with page.expect_navigation(wait_until="networkidle", timeout=120000):
        action()
    time.sleep(pause)
    if not page.query_selector(AC_SEL):
        raise CrawlError(f"server error page: {page.title()[:120]}")


def crawl_ac(page, value, label, pause):
    """Crawl all pages of one AC from a fresh page load and return its rows and manifest rows."""
    ac_no = int(value)
    page.goto(URL, wait_until="networkidle")
    time.sleep(pause)
    postback(page, lambda: page.select_option(AC_SEL, value=value), pause)
    rows, pages = [], {}
    while page.query_selector(GRID):  # No grid means the AC has no BLO rows.
        g = page.eval_on_selector(GRID, READ_GRID)
        if g["current"] in pages:
            raise CrawlError(f"pager went back to page {g['current']}")
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        pages[g["current"]] = dict(ac_no=ac_no, ac_label=label, page=g["current"], rows=len(g["data"]),
                                   sha1=hashlib.sha1(g["html"].encode()).hexdigest(), fetched_at=fetched_at)
        (OUT / "html" / f"AC{ac_no:03d}_p{g['current']:02d}.html").write_text(page.content(), encoding="utf-8")
        rows += [{**dict(zip(COLS, r)), "fetched_at": fetched_at} for r in g["data"]]
        if g["next"] is None:
            break
        postback(page, lambda: page.click(f"{GRID} [data-next]"), pause)

    if pages and sorted(pages) != list(range(1, len(pages) + 1)):
        raise CrawlError(f"pages not 1..N: {sorted(pages)}")
    nums = [int(r["part_no"]) for r in rows]
    if len(set(nums)) != len(nums):
        raise CrawlError("duplicate part numbers")
    return rows, [pages[k] for k in sorted(pages)]


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--acs", nargs="*", type=int, help="AC numbers to crawl (default: all)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between requests")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--force", action="store_true", help="crawl ACs that are already saved")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    for d in ("html", "acs"):
        (OUT / d).mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle")
        for value, label in ac_options(page):
            ac_no = int(value)
            done = OUT / "acs" / f"AC{ac_no:03d}.csv"
            if (args.acs and ac_no not in args.acs) or (done.exists() and not args.force):
                continue
            for attempt in range(1, args.retries + 1):
                for f in (OUT / "html").glob(f"AC{ac_no:03d}_p*.html"):
                    f.unlink()  # Remove pages left by an earlier incomplete attempt.
                try:
                    rows, pages = crawl_ac(page, value, label, args.delay)
                    break
                except Exception as e:  # Error page, timeout or broken pager.
                    print(f"AC {ac_no:>2}: attempt {attempt} failed: {type(e).__name__}: {str(e)[:150]}", flush=True)
                    if attempt == args.retries:
                        raise
                    time.sleep(10 * attempt)
            write_csv(OUT / "acs" / f"AC{ac_no:03d}_manifest.csv", MANIFEST_COLS, pages)
            write_csv(done, [*COLS, "fetched_at"], rows)
            nums = [int(r["part_no"]) for r in rows]
            span = f"parts {min(nums)} to {max(nums)}" if nums else "no rows"
            print(f"AC {ac_no:>2} {label}: {len(rows)} rows on {len(pages)} pages, {span}", flush=True)
        browser.close()

    # Combine every saved AC in AC order.
    rows, manifest = [], []
    for f in sorted((OUT / "acs").glob("AC???.csv")):
        with open(f, encoding="utf-8") as fh:
            rows += list(csv.DictReader(fh))
        with open(f.with_name(f.stem + "_manifest.csv"), encoding="utf-8") as fh:
            manifest += list(csv.DictReader(fh))
    write_csv(OUT / "blo_tables.csv", [*COLS, "fetched_at"], rows)
    write_csv(OUT / "manifest.csv", MANIFEST_COLS, manifest)
    print(f"Wrote {len(rows)} rows from {len({m['ac_no'] for m in manifest})} ACs to {OUT / 'blo_tables.csv'}")


if __name__ == "__main__":
    main()
