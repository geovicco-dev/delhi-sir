"""Download every part-wise PDF from CEO Delhi's SIR 2026 notices page, skipping files on disk."""

import argparse
import csv
import hashlib
import random
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from direct_proxy import start_proxy

URL = "https://ceodelhinet.nic.in/ceodelhiweb/Notices_Issuedn.aspx"
DISTRICT_SEL = "#ctl00_ContentPlaceHolder1_ddlDistrict"
AC_SEL = "#ctl00_ContentPlaceHolder1_ddlACNO"
GRID = "#ctl00_ContentPlaceHolder1_gvContactEntryModule"
OUT = Path("raw/notices_pdfs")  # Git-ignored because the PDFs contain names and EPIC numbers.
MANIFEST = OUT / "manifest.csv"
FIELDS = ["district", "ac_no", "ac_name", "part_no", "part_name", "url", "file",
          "bytes", "sha1", "fetched_at", "status"]


def options(page, selector):
    return page.eval_on_selector(
        selector,
        "s => [...s.options].map(o => [o.value, o.textContent.trim()]).filter(o => o[0] && o[0] !== '0')",
    )


def choose(page, selector, value, pause):
    with page.expect_navigation(wait_until="networkidle", timeout=120000):
        page.select_option(selector, value=value)
    time.sleep(pause)


def grid_rows(page):
    if not page.query_selector(GRID):
        return []
    return page.eval_on_selector(
        GRID,
        """g => [...g.querySelectorAll('tr')].slice(1).map(tr => {
              const td = tr.querySelectorAll('td'), a = tr.querySelector('a[href]');
              return td.length >= 3 ? {part_no: td[0].innerText.trim(), part_name: td[1].innerText.trim(),
                                       url: a ? a.href : ''} : null;
           }).filter(Boolean)""",
    )


def load_done():
    done = set()
    if MANIFEST.exists():
        with open(MANIFEST, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["status"] == "ok":
                    done.add((r["ac_no"], r["part_no"]))
    return done


def fetch_plain(page, url, proxy_url):
    """Fetch one PDF with Python's HTTP client, reusing the browser's cookies and proxy."""
    cookies = "; ".join(f"{c['name']}={c['value']}" for c in page.context.cookies(url))
    headers = {"User-Agent": page.evaluate("navigator.userAgent"), "Cookie": cookies}
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"https": proxy_url} if proxy_url else {}))
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=120) as resp:
            body = resp.read()
    except Exception:
        return None
    return body if body[:4] == b"%PDF" and b"%%EOF" in body[-2048:] else None


def fetch(page, url, proxy_url=None, retries=3):
    status = ""
    for attempt in range(1, retries + 1):
        try:
            resp = page.context.request.get(url, timeout=120000)
            body = resp.body()
            if resp.ok and body[:4] == b"%PDF":
                return body, "ok"
            status = f"http {resp.status}, {resp.headers.get('content-type')}"
        except Exception as e:  # Network error.
            status = f"error {str(e).splitlines()[0]}"
            if "Parse Error" in status:
                # Retry once with Python's HTTP client, since Chromium rejects some responses as malformed.
                body = fetch_plain(page, url, proxy_url)
                return (body, "ok") if body else (None, status)
        time.sleep(5 * attempt)
    return None, status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--acs", nargs="*", help="AC numbers to crawl (default: all)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between downloads")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--interface", help="send the crawl's traffic out through this network interface")
    args = ap.parse_args()
    wanted = {str(int(a)) for a in args.acs} if args.acs else None
    proxy = {"server": start_proxy(args.interface)} if args.interface else None
    failed_parts = 0

    OUT.mkdir(exist_ok=True)
    done = load_done()
    new_file = not MANIFEST.exists()
    mf = open(MANIFEST, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(mf, fieldnames=FIELDS)
    if new_file:
        w.writeheader()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed, proxy=proxy)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle")
        for d_val, d_label in options(page, DISTRICT_SEL):
            page.goto(URL, wait_until="networkidle")
            choose(page, DISTRICT_SEL, d_val, args.delay)
            for ac_val, ac_label in options(page, AC_SEL):
                if wanted and ac_val not in wanted:
                    continue
                if page.input_value(DISTRICT_SEL) != d_val:
                    choose(page, DISTRICT_SEL, d_val, args.delay)
                choose(page, AC_SEL, ac_val, args.delay)
                # Skip the trailing pager or footer row, which has no part number.
                rows = [r for r in grid_rows(page) if r["part_no"].isdigit()]
                ac_name = ac_label.split("-", 1)[-1].strip()
                todo = [r for r in rows if (ac_val, r["part_no"]) not in done]
                print(f"{d_label} / {ac_label}: {len(rows)} parts, {len(todo)} to fetch", flush=True)
                for r in todo:
                    dest = OUT / f"AC{int(ac_val):03d}" / f"AC{int(ac_val):03d}_P{int(r['part_no']):04d}.pdf"
                    dest.parent.mkdir(exist_ok=True)
                    body, status = fetch(page, r["url"], proxy and proxy["server"]) if r["url"] else (None, "no link")
                    if body:
                        dest.write_bytes(body)
                    w.writerow({
                        "district": d_label, "ac_no": ac_val, "ac_name": ac_name,
                        "part_no": r["part_no"], "part_name": r["part_name"], "url": r["url"],
                        "file": str(dest) if body else "", "bytes": len(body) if body else 0,
                        "sha1": hashlib.sha1(body).hexdigest() if body else "",
                        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "status": status,
                    })
                    mf.flush()
                    if status != "ok":
                        failed_parts += 1
                        print(f"   ! part {r['part_no']}: {status}", flush=True)
                    time.sleep(args.delay + random.uniform(0, 1))
        browser.close()
    mf.close()
    if failed_parts:
        # Exit non-zero so the background service retries the failed parts later.
        sys.exit(f"Done, but {failed_parts} parts failed this run; re-run to retry them.")
    print("Done. Every listed part is downloaded.")


if __name__ == "__main__":
    main()
