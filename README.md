# Delhi SIR 2026: data and processing scripts

Data, and the scripts that fetch, parse and process it, for work on the Special Intensive Revision (SIR) of Delhi's electoral roll in 2026.

## Organisation

```
common/                           Shared by every topic
  scripts/electoral-roll/         Download, parse and count the notice and ASDD lists
  scripts/polling-stations/       Download the polling station list and locate each station
  data/electoral-roll/            Counts by polling station and constituency, by reason, gender and age band
  data/polling-stations/          Polling station list, locations, old-to-current part numbers
  data/boundaries/                Assembly constituency boundaries

topics/
  voter-lists/                    Voters left out of the draft roll or sent a notice, by polling station
  cec-resignation-protest/        Train cancellations and metro closures on 10 October 2026
```

`common/` holds the SIR data that any story can use. Each folder in `topics/` is one piece of work and says which `common/` data it used. Each folder's README describes how it is organised, the method step by step, and where each dataset came from and when.

The person-level lists, with names and voter ID numbers, are not in this repository. Only counts are.

These are unofficial counts, not affiliated with CEO Delhi, the Election Commission of India, Indian Railways or DMRC. To check your own enrolment, use https://electoralsearch.eci.gov.in/.

## Licences

Code is under the MIT licence (`LICENSE`). Data made here is under CC BY-SA 4.0, with credit to ecotrakr. Data from other sources keeps its own licence; see `DATA-LICENCE.md`.

## Questions

Open an issue on this repository.
