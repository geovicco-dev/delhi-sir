#!/usr/bin/env bash
# Re-fetch the raw datasets and write a dated checksum log.
set -euo pipefail
cd "$(dirname "$0")/.."
UA="delhi-sir-research/1.0"
OVERPASS="${OVERPASS:-https://overpass-api.de/api/interpreter}"
BBOX="28.35,76.85,28.95,77.60"  # South, west, north, east around Delhi and its satellite cities.

mkdir -p data/raw/datameet data/raw/osm

# R1: fetch datameet's Indian Railways stations at a pinned commit.
DATAMEET_COMMIT="e0c538a1e41ae5eace454d2818902e1065608e16"
curl -sSfL -o data/raw/datameet/stations.json \
  "https://raw.githubusercontent.com/datameet/railways/${DATAMEET_COMMIT}/stations.json"

# R2: fetch Delhi Metro route relations with member geometry from OSM.
curl -sSf -A "$UA" -o data/raw/osm/delhi_metro_routes.json "$OVERPASS" \
  --data-urlencode "data=[out:json][timeout:100];relation[\"route\"=\"subway\"](${BBOX});out geom;"

# R3: fetch the tags of every stop node in those routes.
curl -sSf -A "$UA" -o data/raw/osm/delhi_metro_stop_tags.json "$OVERPASS" \
  --data-urlencode "data=[out:json][timeout:100];rel[\"route\"=\"subway\"](${BBOX});node(r:\"stop\");out tags;"

# R8: fetch every rail and metro track way with geometry.
curl -sSf -A "$UA" -o data/raw/osm/delhi_rail_ways.json "$OVERPASS" \
  --data-urlencode "data=[out:json][timeout:180];way[\"railway\"~\"^(rail|subway|narrow_gauge|light_rail|monorail)\$\"](${BBOX});out geom;"

# R9: fetch railway stations and halts.
curl -sSf -A "$UA" -o data/raw/osm/delhi_rail_stations.json "$OVERPASS" \
  --data-urlencode "data=[out:json][timeout:100];nwr[\"railway\"~\"^(station|halt)\$\"](${BBOX});out center tags;"

# R10: fetch the NCT of Delhi boundary as OSM XML.
curl -sSf -A "$UA" -o data/raw/osm/delhi_nct_boundary.osm "$OVERPASS" \
  --data-urlencode "data=[timeout:100];relation[\"boundary\"=\"administrative\"][\"admin_level\"=\"4\"][\"name:en\"=\"Delhi\"];(._;>;);out body;"

# R11: fetch track under construction or proposed.
curl -sSf -A "$UA" -o data/raw/osm/delhi_rail_planned.json "$OVERPASS" \
  --data-urlencode "data=[out:json][timeout:90];way[\"railway\"~\"^(construction|proposed)\$\"](${BBOX});out geom;"

{ date -u +"%Y-%m-%dT%H:%M:%SZ"; sha256sum data/raw/datameet/stations.json data/raw/osm/*.json data/raw/osm/*.osm; } \
  | tee "data/raw/fetch_log_$(date -u +%Y%m%dT%H%M%SZ).txt"

# R4: fetch DMRC's official network map raster, which is kept out of git.
mkdir -p data/raw/dmrc
curl -sSfL -A "$UA" -o data/raw/dmrc/DMRC-NMRC-and-NCRTC-MAP-10.09.2026.jpg \
  "https://delhimetrorail.com/static/media/DMRC-NMRC-and-NCRTC-MAP-10.09.2026.3fc17df1.jpg"
sha256sum data/raw/dmrc/*.jpg

# R6: fetch DMRC's journey-planner map bundle; update the hashed chunk names if they 404.
mkdir -p data/raw/dmrc/map_bundle
for c in 1.e40bd2b1 10.18d6e9f4; do
  curl -sSfL -A "$UA" -o "data/raw/dmrc/map_bundle/chunk_${c}.js" "https://delhimetrorail.com/static/js/${c}.chunk.js"
done
sha256sum data/raw/dmrc/map_bundle/*.js
