"""Snapshot the DMRC website's public JSON API into a timestamped folder with a manifest."""
import argparse, hashlib, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API = "https://backend.delhimetrorail.com/api/v2/en/"
HEADERS = {
    "Origin": "https://delhimetrorail.com",
    "Referer": "https://delhimetrorail.com/",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) delhi-sir-research/1.0",
}
LINES = [f"LN{i}" for i in range(1, 13)]  # LN13 and above return nothing.
ROOT = Path(__file__).resolve().parents[1]


def get(path):
    req = Request(API + quote(path), headers=HEADERS)  # Quote the path because some station codes contain spaces.
    try:
        with urlopen(req, timeout=30) as r:
            body, status = r.read(), r.status
    except HTTPError as e:
        body, status = e.read(), e.code
    except (URLError, TimeoutError) as e:
        body, status = str(e).encode(), 0
    time.sleep(1)
    return status, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="only line + line-station status")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "data/raw/dmrc/api" / (stamp + ("_status" if args.status else "_full"))
    out.mkdir(parents=True)
    manifest = {"fetched_at_utc": stamp, "api_base": API, "request_headers": HEADERS, "files": []}

    paths = []
    for ln in LINES:
        paths += [f"metro_line/{ln}", f"station_by_line_linepage/{ln}"]
    if not args.status:
        paths.append("station_list")

    def save(path):
        status, body = get(path)
        fname = path.replace("/", "__") + ".json"
        (out / fname).write_bytes(body)
        ok = status == 200 and body[:1] in (b"[", b"{")
        manifest["files"].append({"path": path, "url": API + quote(path), "file": fname, "http_status": status,
                                  "json": ok, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                                  "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
        print(f"{status} {'ok ' if ok else 'BAD'} {path}", file=sys.stderr)
        return json.loads(body) if ok else None

    for p in paths:
        data = save(p)
        if p == "station_list" and data:
            for st in data:
                save(f"station_brief_detail/{st['station_code']}")

    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    bad = [f["path"] for f in manifest["files"] if not f["json"]]
    print(f"{len(manifest['files'])} files -> {out.relative_to(ROOT)}; failures: {bad or 'none'}")


if __name__ == "__main__":
    main()
