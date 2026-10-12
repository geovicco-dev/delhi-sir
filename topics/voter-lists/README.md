# Voters left out or sent a notice, by polling station

Three maps of Delhi's 14,947 polling stations, made from the two SIR lists: voters left out of the draft roll (the ASDD list) and voters sent a notice. All the data comes from `common/`; this topic adds no data of its own.

## The three maps

| Map | What it counts | Result |
|---|---|---|
| 1 | Stations where voters left out plus voters sent a notice reach 600, half of a full station of 1,200 | 5,565 of 14,947 stations |
| 2 | Stations where 600 or more voters were left out | 639 stations |
| 3 | Stations where 24 or fewer voters were left out, 2% of 1,200 | 51 stations |

Each map draws one point per polling location, a building that holds 1 to 19 stations. 2,665 locations, holding 13,934 stations, have a point. A location is highlighted if any one of its stations passes that map's threshold, and sized by the total across all its stations.

## Data used

| File in `common/` | Used for |
|---|---|
| `data/electoral-roll/asdd_by_part.csv` | Voters left out, per station, and the split by reason for map 2 |
| `data/electoral-roll/notices_by_part.csv` | Voters sent a notice, per station, for map 1 |
| `data/electoral-roll/ac_uncollectable_31aug2026.csv` | The roll before the revision, by district and constituency |
| `data/polling-stations/parts_located.csv`, `polling_sites.geojson` | Where each station is |
| `data/boundaries/datameet-india-ac/` | Constituency boundaries |

## Method

1. Join the ASDD and notice counts per station on `ac_no` and `part_no`.
2. Add the two. A notice goes to a voter still on the draft roll, and the ASDD list holds voters left off it, so no voter is on both.
3. Polling station sizes are not published, so each station's share is taken against CEO Delhi's cap of 1,200 voters. A station with fewer voters has a higher real share, so maps 1 and 2 give minimums and map 3's count is a maximum.
4. Map 3's threshold follows the 2% check in the ECI's electoral roll FAQ (questions 8 and 9), which cites its instruction of 11 August 2023.
5. Group stations into locations with `site_id` from `parts_located.csv`, and keep only points that fall inside their own constituency.

## Limits

- 1,013 stations have no point: 698 whose point fell outside their own constituency, and 315 not found. Their counts are in the totals but not on the maps.
- Points matched to the 2017 polling station list can be out of date where a school or office has moved.
- Reasons are counted as printed on the lists. They were not checked.
- See `common/README.md` for how each count and location was made.
