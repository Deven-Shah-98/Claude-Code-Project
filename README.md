# Stadium Effect Atlas

How do pro sports venues (and winning) relate to nearby housing markets? Public data only.

## Data sources
| Need | Source |
|---|---|
| Home values by ZIP | Zillow Research ZHVI (`files.zillowstatic.com`) |
| ZIP centroids | US Census 2020 ZCTA Gazetteer (`www2.census.gov`) |
| Venues | `data/seed/venues.csv` (hand-curated; coordinates **unverified**, to be checked against OSM/Wikidata) |

## Method
For each venue, ZIP centroids are bucketed into distance rings (0-1.5, 1.5-3, 3-5 mi) with a 5-15 mi
control donut. We estimate a difference-in-differences on log home values (3 years before vs. months
25-36 after opening) with a bootstrap CI over ZIPs, plus a pre-trend diagnostic. This is an association,
not proof of causation: stadiums are often built where redevelopment is already underway.

## Usage
```
pip install -e ".[dev]"
atlas fetch              # download raw data to data/raw
atlas score              # effect table for all seeded venues
atlas score --venue oracle-park
pytest
```

## Roadmap
1. ~~Pipeline, ring assignment, DiD + event study, tests~~
2. Real-data run and venue coordinate verification
3. Synthetic-control comparison
4. 3D time-lapse map (MapLibre/deck.gl) and event-study charts
5. Natural-language query layer
