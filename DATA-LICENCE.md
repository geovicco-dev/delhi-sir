# Data licences

Data made in this repository (the counts, the polling station locations, the hand-compiled tables and the processed layers) is licensed under Creative Commons Attribution-ShareAlike 4.0, https://creativecommons.org/licenses/by-sa/4.0/. Credit: ecotrakr.

Data from other sources keeps its own terms.

| Source | Files | Terms |
|---|---|---|
| Chief Electoral Officer, Delhi, and the Election Commission of India | Counts in `common/data/electoral-roll/`, `common/data/polling-stations/ceo-delhi-psl/` | Public government publications. The person-level lists are counted, not redistributed |
| DataMeet, assembly constituency boundaries | `common/data/boundaries/datameet-india-ac/`, and the geometry in `common/data/boundaries/delhi_ac_uncollectable.geojson` | CC BY 2.5 India |
| DataMeet, railway station coordinates | `topics/cec-resignation-protest/data/raw/datameet/stations.json` | CC0 1.0 |
| OpenStreetMap contributors | `topics/cec-resignation-protest/data/raw/osm/`, the layers built from them, and the geocoded points in `common/data/polling-stations/` | ODbL 1.0, https://opendatacommons.org/licenses/odbl/ |
| ECI 2017 polling station list, as scraped by aaronrudkin/IndianPollingStations | Coordinates of 13,270 polling stations in `common/data/polling-stations/` | No licence stated. The list itself is not included; `common/data/polling-stations/eci-2017/manifest.json` gives its URL and checksum |
| DMRC, Northern Railway, etrain.info and news reports | Facts in `topics/cec-resignation-protest/data/curated/` | Facts as published, each cited in `sources.csv` or by DMRC post id |
