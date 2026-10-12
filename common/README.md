# Common data: the SIR lists, polling stations and boundaries

During the Special Intensive Revision (SIR) of Delhi's electoral roll in 2026, two person-level lists were published, each as one PDF per polling station:

- the ASDD list (Absent, Shifted, Dead, Duplicate): voters on the roll before the revision whose enumeration form was not collected, and who are left out of the draft roll of 31 August 2026;
- the notice list: voters on the draft roll who were sent a notice, with the reason printed against each entry.

This folder holds the scripts that download and parse both lists, the counts made from them, and the polling station and boundary data they are mapped with. Every story in `topics/` reads its data from here. The lists themselves, with names and voter ID numbers, are not published.

## Organisation

```
scripts/electoral-roll/     Download, parse and count the notice and ASDD lists
scripts/polling-stations/   Download the polling station list, normalise it, locate each station,
                            and link old to current part numbers
data/electoral-roll/        Counts per polling station and per constituency, and CEO Delhi's
                            draft roll counts by constituency
data/polling-stations/      CEO Delhi's polling station list, a point location for each station,
                            and the old-to-current part map
data/boundaries/            Assembly constituency boundaries
requirements.txt            Python packages
```

The scripts write the PDFs to `raw/` and the parsed lists to `processed/`. Both hold names and voter ID numbers and are not part of this repository.

Polling stations are called parts in the source lists, and `part_no` is the polling station number. In August 2026, stations were capped at 1,200 voters and renumbered, from 13,033 old parts to 14,947 current parts. Every file here uses the current numbers unless a column says `old_part_no`.

## Method

Set up once:

    python -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/playwright install chromium

All commands run from this folder (`common/`).

### 1. Download

Each crawl requests the same public pages and files a person would, one at a time and at least two seconds apart. No CAPTCHA is solved or submitted. Every download is recorded in a `manifest.csv` with its URL, size, SHA-1 and download time, so a republished list can be detected.

    python scripts/polling-stations/crawl_psl.py     # polling station list, 70 constituencies -> raw/psl/psl_tables.csv
    python scripts/electoral-roll/crawl_notices.py   # notice PDFs, about 10-12 hours -> raw/notices_pdfs/
    python scripts/electoral-roll/crawl_asdd.py      # ASDD PDFs, about 11-12 hours -> raw/asdd_pdfs/
    python scripts/polling-stations/crawl_blo.py     # booth level officer list -> raw/blo/

`crawl_notices.py --acs 41` downloads a single constituency as a test. Re-running any crawl skips files already on disk. `crawl_notices.py --interface <name>` sends the crawl through one network interface, using `direct_proxy.py`.

### 2. Parse

    python scripts/electoral-roll/parse_notices.py raw/notices_pdfs processed/notices.csv
    python scripts/electoral-roll/parse_asdd.py raw/asdd_pdfs processed/asdd.csv
    python scripts/polling-stations/normalise_psl.py

The parsers read each PDF into one row per voter, keeping the part number, serial number, age, gender and the reason printed against the entry. A notice can carry several reasons separated by commas, and each is kept. The ASDD list prints each voter's old and new part number. The PDFs are text, so no OCR is used.

### 3. Count

    python scripts/electoral-roll/aggregate_notices.py
    python scripts/electoral-roll/aggregate_asdd.py
    python scripts/electoral-roll/aggregate_reasons.py
    python scripts/polling-stations/build_part_map.py

These write the counts to `data/electoral-roll/` and the part map to `data/polling-stations/`. No name, voter ID number or other person-level field reaches any output. Every count is published as counted, including small ones.

### 4. Locate

    python scripts/polling-stations/locate_parts.py --geocode --email <your contact address>

This gives each polling station a point. Stations that share a building are placed together, as one polling location.

1. Each station's building, locality and part name are matched against the localities of the 2017 polling stations in the same constituency (fuzzy match, score 85 or more out of 100). Near-ties are broken by the station's relative position in the constituency's part numbering. A location takes the 2017 point that most of its stations matched.
2. Locations with no match are geocoded with OpenStreetMap's Nominatim, trying building and locality, then locality, then part name, within the constituency's bounding box. Requests are just over one second apart, and Nominatim asks for a contact address in each.
3. A point that falls outside its own constituency is kept but flagged, and not used.

The 2017 list is not included here (see Datasets). `locate_parts.py --ref` takes a CSV of its Delhi rows with `ac_no`, `part_no`, `ps_locality`, `lat` and `lon`.

| Result | Stations |
|---|---|
| Matched to the 2017 list | 13,270 |
| Geocoded by locality | 407 |
| Geocoded by part name | 248 |
| Geocoded by building | 9 |
| Point outside its own constituency, not used | 698 |
| Not found | 315 |

## Datasets

### Notices by polling station and constituency

Files: `data/electoral-roll/notices_by_part.csv`, `notices_by_ac.csv`

| | |
|---|---|
| Source | CEO Delhi, "List of Persons to Whom Notices Have Been Issued", published 19 September 2026, https://ceodelhinet.nic.in/ceodelhiweb/Notices_Issuedn.aspx |
| Downloaded | 27-28 September 2026, all 14,947 polling stations in 70 constituencies |
| Made by | `crawl_notices.py`, `parse_notices.py`, `aggregate_notices.py` |
| Checksums | `source_sha1` is the SHA-1 of each station's PDF. In the constituency file it is the SHA-1 of that constituency's station hashes, joined by newlines in part order |
| Check | The PDFs hold 33,11,746 notices. CEO Delhi's published total is 33,12,919, so 1,173 are missing from the PDFs. The difference is not explained |

Columns: `ac_no`, `ac_name`, `part_no`, `part_name`; `notices_total`; one `reason_*` column per reason; `notices_male`, `notices_female`, `notices_third_gender` (printed M, F, O); eight age bands from `age_18_19` to `age_80_plus`; `median_age`; `crawl_date`; `source_sha1`. The constituency file adds `parts`.

A notice can give more than one reason. It counts once in `notices_total` and once in each of its reason columns, so the reason columns can add up to more than the total.

| Column | Reason as printed |
|---|---|
| `reason_unmapped` | Unmapped with Last SIR |
| `reason_self_name_mismatch` | Self Name Mismatch |
| `reason_parent_name_mismatch` | Parent Name Mismatch |
| `reason_progeny_age_gap_lt_9_months` | Progeny Age Gap <9 Month |
| `reason_parent_age_diff_lt_15` | Parent Age Difference <15 |
| `reason_progeny_ge_6` | Progeny >= 6 |
| `reason_parent_age_diff_gt_50` | Parent Age difference >50 |
| `reason_grandparent_age_diff_lt_40` | Grandparent Age difference <40 |
| `reason_parent_ineligible` | Parent Marked ineligible in Last SIR |
| `reason_none` | Reason cell left blank |

### ASDD list by polling station and constituency

Files: `data/electoral-roll/asdd_by_part.csv`, `asdd_by_ac.csv`

| | |
|---|---|
| Source | Election Commission of India, one PDF per polling station on voters.eci.gov.in, linked from CEO Delhi's ASDD page, https://ceodelhi.gov.in/ceodelhiasdd/ |
| Downloaded | 27-28 September 2026, all 14,947 polling stations |
| Made by | `crawl_asdd.py`, `parse_asdd.py`, `aggregate_asdd.py` |
| Check | 47,56,722 voters. The count in every constituency equals CEO Delhi's count of uncollectable forms for it on 31 August 2026 (`data/electoral-roll/ac_uncollectable_31aug2026.csv`) |

Columns are as for notices, with `asdd_` in place of `notices_`, and `old_parts`, the number of old parts the station's voters were listed in. Each voter has one reason, so the reason columns add up to `asdd_total`.

| Column | Reason as printed |
|---|---|
| `reason_shifted` | Permanently Shifted |
| `reason_absent` | Untraceable/Absent |
| `reason_dead` | Death |
| `reason_duplicate` | Already enrolled |

### Counts by reason, gender and age band

Files: `data/electoral-roll/reasons_by_part.csv`, `reasons_by_ac.csv`

| | |
|---|---|
| Source | The same parsed lists as above |
| Made by | `aggregate_reasons.py` |

`reasons_by_part.csv` has one row per list (`notice` or `asdd`), polling station and reason, with `reason = all` for everyone on the list, and 24 columns from `male_18_19` to `third_gender_80_plus` that add up to `total`. `reasons_by_ac.csv` has one row per list, constituency, reason, gender and age band, with a `count`. Both include zero rows. The constituency file is the sum of its stations.

### Old to current polling station numbers

File: `data/polling-stations/part_map.csv`

| | |
|---|---|
| Source | The old and new part numbers printed against each voter in the ASDD PDFs |
| Made by | `build_part_map.py` |

One row per pair of current part and old part, with the number of ASDD voters linking them. `one_blo` is true where a current part takes its voters from a single old part and has at least 30 ASDD voters, so one booth level officer most likely covered it before and after the renumbering.

### Polling station locations

Files: `data/polling-stations/parts_located.csv` (one row per polling station), `data/polling-stations/polling_sites.geojson` (one point per polling location, 2,784 points)

| | |
|---|---|
| Sources | ECI 2017 polling station list, as scraped by aaronrudkin/IndianPollingStations; OpenStreetMap Nominatim |
| Made by | `locate_parts.py`, early October 2026 |

`method` says how each point was found (`psleci_2017`, `nominatim_locality`, `nominatim_part_name`, `nominatim_building`, or blank when not found). `score` is the name-match score out of 100. `site_id` links each station to its point in `polling_sites.geojson`. `in_ac` is false where the point falls outside the station's own constituency. The 2017 points can be out of date where a school or office has moved.

### Reference tables

| File | Source | Retrieved | Notes |
|---|---|---|---|
| `data/polling-stations/ceo-delhi-psl/polling_stations_psl.csv` | CEO Delhi polling station list, https://ceodelhinet.nic.in/ceodelhiweb/PSL.aspx | 27 September 2026 | 14,947 stations with locality, polling area and address. Written by `crawl_psl.py`; `manifest.csv` has the row count and SHA-1 per constituency |
| `data/electoral-roll/ac_uncollectable_31aug2026.csv` | CEO Delhi, draft roll counts and uncollectable forms per constituency, 31 August 2026 | Transcribed by hand | Voters on the draft roll by gender, and uncollectable forms, for 70 constituencies, with one subtotal row per district (blank `AC_No`) |
| `data/boundaries/datameet-india-ac/` | DataMeet, assembly constituency boundaries, https://github.com/datameet/maps, commit `7a1c21c` | 3 October 2026 | 2008 delimitation. DataMeet's own README and licence are included. `manifest.json` gives each file's URL and SHA-1 |
| `data/boundaries/delhi_ac_uncollectable.geojson` | The 70 Delhi boundaries from the DataMeet layer, joined to the 31 August counts | | `locate_parts.py` uses it to check each point falls in its own constituency |
| `data/polling-stations/eci-2017/manifest.json` | aaronrudkin/IndianPollingStations, commit `22400cd` | 3 October 2026 | URL, size and SHA-1 of the file used. The file itself is not included, because it states no licence |

## Limits

- These are unofficial counts, made from the lists as published on the dates above. Later changes to either list are not reflected.
- Reasons are counted as printed. They were not checked.
- Polling station sizes are not published, so shares at station level use the 1,200-voter cap as the base. A station with fewer voters has a higher real share.
- The draft roll has no ages, and there are no published draft roll counts per station, so age bands and station-level figures give shares within a list.
