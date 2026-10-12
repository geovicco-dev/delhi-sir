# The CEC resignation protest: train cancellations and metro closures, Delhi, 10 October 2026

On 10 October 2026, ahead of a protest at Jantar Mantar demanding the resignation of the Chief Election Commissioner, the Railway Board cancelled 38 of the 165 Mail/Express trains due into New Delhi and Hazrat Nizamuddin between 04:00 and 14:00, and DMRC shut the gates of 45 metro stations, from a list of 57 that Delhi Police had asked for.

This topic covers both. It holds the data, and the scripts that fetch and process it. It does not use the SIR lists in `common/`.

## Organisation

```
data/raw/         Files as downloaded and never edited: DataMeet station coordinates and
                  OpenStreetMap extracts. Re-download with scripts/fetch_raw.sh
data/curated/     Tables compiled by hand from news reports, official statements and DMRC's
                  posts. Each row cites its sources
data/processed/   Files written only by the scripts. Any of them can be deleted and rebuilt
scripts/          Fetch, parse and build scripts, described below in the order they run
requirements.txt  Python packages. build_context_layers.py also needs GDAL's ogr2ogr
```

Distances to Jantar Mantar are straight-line (haversine) distances from 77.2166 E, 28.6271 N, the centroid of the OpenStreetMap outline of the observatory (way 223456559), rounded to four decimals.

## Method

All commands run from this folder.

### 1. Fetch

    bash scripts/fetch_raw.sh
    python scripts/fetch_etrain.py
    python scripts/fetch_dmrc.py

`fetch_raw.sh` downloads DataMeet's railway stations at a fixed commit, runs six Overpass queries against OpenStreetMap, and downloads DMRC's network map and the two JavaScript files of DMRC's journey planner that carry its station register. It writes a log with the time and SHA-256 of each file.

`fetch_etrain.py` saves the etrain.info page of each train in `data/curated/cancelled_trains.csv`, and the seat-map page and image of each coach type, at one request per second.

`fetch_dmrc.py` saves DMRC's public website API (lines, stations and live status) into a timestamped folder with a manifest. `--status` saves only line and station status. The build scripts do not read these snapshots. They were used to check station names and status.

DMRC's files and the etrain pages are not included here, because they are copies of third-party websites. Re-running the fetch scripts downloads them again, but those sites may have changed since October 2026.

### 2. Compile by hand

The six tables in `data/curated/` were compiled by reading documents, not by a script. Each is described under Datasets.

### 3. Build

    python scripts/extract_dmrc_vector.py
    python scripts/build_datasets.py
    python scripts/build_context_layers.py
    python scripts/parse_etrain.py

`extract_dmrc_vector.py` reads DMRC's station register out of the journey planner's JavaScript and writes `dmrc_network.json`.

`build_datasets.py` writes the cancelled train lines, the metro lines and stops, and the Delhi terminals table. Station names are matched to OpenStreetMap stops with `metro_match.py`, which normalises spelling and holds a short table of known spelling differences.

`build_context_layers.py` writes the rail, metro, planned-line and boundary layers, and joins DMRC's register to OpenStreetMap positions.

`parse_etrain.py` reads the saved etrain pages and writes the coach-by-coach and per-train seat tables.

## Datasets

### Raw

| File | Source | Retrieved | SHA-256 | Licence |
|---|---|---|---|---|
| `data/raw/datameet/stations.json` | DataMeet railways, https://github.com/datameet/railways, commit `e0c538a` | 9 Oct 2026, 12:54 UTC | `9bd5e1da3a859e5359a95f40b6009aa468efb177da4faac57ffdcd7daeb4df18` | CC0 1.0 |
| `data/raw/osm/delhi_metro_routes.json` | OpenStreetMap via Overpass: metro route relations with geometry | OSM data as of 9 Oct 2026, 12:53 UTC | `53b689deef95bf23e2ad0be42ac8332912871a7cb1db730a2f12bc5bf12c6aac` | ODbL 1.0 |
| `data/raw/osm/delhi_metro_stop_tags.json` | OpenStreetMap via Overpass: tags of every stop in those routes | 9 Oct 2026, 12:56 UTC | `fba390037689f85ac30f7bbf7d2297f67e5745ae5652eb69bc31bfa23ec5edca` | ODbL 1.0 |
| `data/raw/osm/delhi_rail_ways.json` | OpenStreetMap via Overpass: rail and metro track | 9 Oct 2026, 13:33 UTC | `8878994e94f2d34b9525e19709b158e16664cf78384b2f808cc5a7773f909d7d` | ODbL 1.0 |
| `data/raw/osm/delhi_rail_stations.json` | OpenStreetMap via Overpass: railway stations and halts | 9 Oct 2026, 13:33 UTC | `59b9d44b081ae2cb779aff48d54fb8ebca80870345c5a6829c983019a8bf0850` | ODbL 1.0 |
| `data/raw/osm/delhi_nct_boundary.osm` | OpenStreetMap via Overpass: NCT of Delhi boundary relation | 9 Oct 2026, 13:34 UTC | `30343673cbbaa4948ace6ae0f3b5fc9afeeefe85cefd74fb7298b36c2b16c140` | ODbL 1.0 |
| `data/raw/osm/delhi_rail_planned.json` | OpenStreetMap via Overpass: track under construction or proposed | 9 Oct 2026, 14:13 UTC | `1cba103d1a64413a36766cab105f1c69bb76179ca755516deab1629886dfcd67` | ODbL 1.0 |

All Overpass queries cover the box 28.35-28.95 N, 76.85-77.60 E. The exact queries are in `scripts/fetch_raw.sh`. OpenStreetMap is a live database, so a re-run returns current data, not these snapshots. DataMeet's station list was compiled around 2016, so codes renamed since then are missing; `cancelled_trains.csv` records the older code used in `coord_code`.

### Cancelled trains (`data/curated/cancelled_trains.csv`)

| | |
|---|---|
| Source | About 20 news reports carrying zonal railway notices (ECR, ER, NER, NR, NCR, WCR, WR, NWR, CR, SER), each listed in `sources.csv` |
| Compiled | 9 October 2026 |
| Method | A train is included when at least one opened source names its number as cancelled or rescheduled for 10 October. `source_count` and `sources` record which. Return trips from Delhi, local MEMU/EMU services and trains named without a number are left out |
| Check | Northern Railway told PTI on 9 October that 38 of the 165 trains due at New Delhi and Hazrat Nizamuddin between 04:00 and 14:00 were cancelled |
| Limits | No official list was published. The table has 41 rows: 36 trains due at New Delhi or Hazrat Nizamuddin, 3 due at Tilak Bridge and 2 Mumbai Rajdhanis rescheduled by five hours (`category`). That is 39 cancelled candidates against the official 38, and which one is extra is not resolved. Three rows rest on a single source: 12155, 12059 and 82501. Arrival times are filled only where a source gave them |

### Metro closures requested by Delhi Police (`data/curated/metro_closures_requested.csv`)

| | |
|---|---|
| Source | Letter of 8 October 2026 from the Joint Commissioner of Police (Transport), as published by India TV and Outlook on 9 October |
| Method | 57 station names transcribed in the order and spelling of the reports, grouped by area as Outlook grouped them, with one correction: Rithala is placed in West/North-west |
| Limits | The letter itself was not seen, only press transcriptions. This is what was asked for, not what DMRC did |

### Metro closures by DMRC (`data/curated/metro_closures_2026-10-10_dmrc.csv`)

| | |
|---|---|
| Source | DMRC posts on X: 2108483137496060062 (9 Oct 2026, 14:32 IST, 57 stations, listed in an image) and 2108594934387527914 (9 Oct 2026, 21:56 IST, revised list of 45 in the post text) |
| Method | The 57 were transcribed from the image in DMRC's order and checked against the police list. The 45 were parsed from the post text. `in_revised_45` marks the stations in force from 21:00 on 9 October to 18:00 on 10 October. All 57 names match OpenStreetMap stops |
| Use | This table, not the police request, describes what happened. The 12 stations DMRC dropped are all more than 5 km from Jantar Mantar |

### Metro closures for security and protests, 2026 (`data/curated/metro_closures_2026_timeline.csv`)

| | |
|---|---|
| Source | DMRC's posts on X from 29 December 2025 to 10 October 2026, read in full. Each row cites its post ids in `dmrc_posts` |
| Method | One row per day on which DMRC closed gates at one or more stations for security or a protest: 12 days, 23 January to 10 October 2026. `stations_closed_max` is the most stations shut at once that day, including stations added later the same day. Occasions come from news reports where DMRC gave only "security reasons" |
| Limits | No closure posts were found for March to June, August or September 2026 |

### Seats per coach type (`data/curated/coach_capacity.csv`)

| | |
|---|---|
| Source | etrain.info seat-map images, one per coach type. `image_url` and `image_sha256` identify each image |
| Retrieved | 9 October 2026. Values read from the images on 10 October 2026 |
| Check | The 3A and 2A capacities agree with V.K. Saxena, "Types of Passenger Coaches for Different Services" (AITD). The other ten types are not cross-checked |
| Limits | Covers the 12 types used by the trains in `cancelled_trains.csv`. Unreserved general coaches have no seat map on etrain, so no capacity |

### Source register (`data/curated/sources.csv`)

One row per document consulted: `key`, `outlet`, `url`, `used_for`, `opened` and `reliability`. `opened = yes` means the full page was read; `no` means only a search snippet was seen, and such rows support nothing on their own. Reliability is a stated judgement: high for wire services, official bodies and on-record quotes; medium-high for national outlets quoting documents; medium for regional outlets and aggregators; low-medium for small outlets or single sources; low for snippets.

### Processed

| File | Built by | From | What it is |
|---|---|---|---|
| `cancelled_trains.geojson` | `build_datasets.py` | cancelled trains, DataMeet stations | One straight line per train from origin to Delhi terminal, with all columns of the CSV and `distance_km_straight`. Schematic, not the rail route |
| `metro_lines.geojson` | `build_datasets.py` | OSM metro routes | 330 metro track ways with the lines that use them. Delhi-Meerut RRTS is dropped |
| `metro_stations.geojson` | `build_datasets.py` | OSM routes and stop tags, police request | 590 stop nodes. Interchanges and stations mapped per platform appear more than once. `gates_shut_requested` marks the 57 requested stations |
| `delhi_rail_terminals.csv` | `build_datasets.py` | DataMeet stations, OSM stops, Northern Railway statement | The 7 Delhi terminals with their status on 10 October, distance to Jantar Mantar, and the nearest metro stop |
| `dmrc_network.json` | `extract_dmrc_vector.py` | DMRC journey planner | DMRC's station register: 255 stations by official code, with 2026 names, lines, running order, an interchange flag and the 57 requested closures |
| `metro_stations_dmrc.geojson` | `build_context_layers.py` | `dmrc_network.json`, `metro_stations.geojson`, DMRC closures | 275 stations: 253 of DMRC's 255 at the mean of their OSM stop nodes, plus 22 OSM stations DMRC does not run (21 on the Noida Metro Aqua Line, and Haiderpur Village). `gates_shut_dmrc` marks the 45 DMRC shut |
| `metro_station_join.csv` | `build_context_layers.py` | as above | How each DMRC station matched OSM: exact, normalised, alias, unmatched, or OSM-only |
| `metro_tracks.geojson` | `build_context_layers.py` | OSM track and routes | Every metro track way, with line and colour from its route, or from its name, or `Unassigned` |
| `railway_lines.geojson` | `build_context_layers.py` | OSM track | 2,213 non-metro track sections, classed as main line, service track, freight corridor, RRTS or heritage |
| `rail_stations.geojson` | `build_context_layers.py` | OSM stations | 90 named stations: Indian Railways, RRTS and freight corridor. Metro stations are excluded |
| `planned_lines.geojson` | `build_context_layers.py` | OSM planned track | 77 sections tagged under construction or proposed. None of it was open on 10 October |
| `delhi_boundary.geojson` | `build_context_layers.py` | OSM boundary | NCT of Delhi from OpenStreetMap. Not the Survey of India boundary |
| `jantar_mantar.geojson` | `build_context_layers.py` | | The Jantar Mantar point used for every distance |
| `train_rakes.csv` | `parse_etrain.py` | etrain pages, coach capacities | 836 rows: each coach of each train in rake order, with its type and capacity |
| `train_capacity.csv` | `parse_etrain.py` | as above | One row per train: reserved seats at full capacity, coaches counted, general coaches not counted, scheduled arrival. 38 of the 41 trains have a rake listed on etrain |

Seats per train are the sum of the printed capacity of every coach whose type has a seat map. Engines, power, luggage and pantry cars are not passenger coaches. Unreserved general coaches are not counted and are listed in `uncounted_general_coaches`.
