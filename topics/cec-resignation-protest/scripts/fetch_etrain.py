"""Fetch train pages and coach seat maps from etrain.info for seat-capacity estimates."""
import csv, hashlib, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = "https://etrain.info"
UA = "Mozilla/5.0 (X11; Linux x86_64) delhi-sir-research/1.0"
ROOT = Path(__file__).resolve().parents[1]


def get(url):
    try:
        with urlopen(Request(url, headers={"User-Agent": UA}), timeout=30) as r:
            body, status, final = r.read(), r.status, r.geturl()
    except HTTPError as e:
        body, status, final = e.read(), e.code, url
    except (URLError, TimeoutError) as e:
        body, status, final = str(e).encode(), 0, url
    time.sleep(1)
    return status, final, body


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "data/raw/etrain" / stamp
    (out / "trains").mkdir(parents=True)
    (out / "seatmap").mkdir()
    manifest = {"fetched_at_utc": stamp, "user_agent": UA, "files": []}

    def save(url, rel):
        status, final, body = get(url)
        (out / rel).write_bytes(body)
        manifest["files"].append({"url": url, "final_url": final, "file": rel, "http_status": status, "bytes": len(body),
                                  "sha256": hashlib.sha256(body).hexdigest(),
                                  "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
        print(status, rel, file=sys.stderr)
        return status, body

    # Fetch the coach layout index, each type page and its layout image.
    _, idx = save(BASE + "/page/seatmap", "seatmap/index.html")
    types = sorted(set(re.findall(rb'href="/page/seatmap/([A-Za-z0-9_]+)"', idx)))
    for t in (t.decode() for t in types):
        _, page = save(f"{BASE}/page/seatmap/{t}", f"seatmap/{t}.html")
        img = re.search(rb'src="(https://etrain\.info/images/coach-layout/[^"]+)"', page)
        if img:
            save(img.group(1).decode(), f"seatmap/{t}{Path(img.group(1).decode()).suffix}")

    # Fetch the page for each cancelled train.
    trains = [r["train_no"] for r in csv.DictReader(open(ROOT / "data/curated/cancelled_trains.csv"))]
    for no in trains:
        save(f"{BASE}/train/{no}/schedule", f"trains/{no}.html")

    bad = [f["file"] for f in manifest["files"] if f["http_status"] != 200]
    print(f"{len(manifest['files'])} files -> {out.relative_to(ROOT)}; failures: {bad or 'none'}")


if __name__ == "__main__":
    main()
