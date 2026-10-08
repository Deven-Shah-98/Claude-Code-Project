# Stadium Effect Atlas

How do pro sports venues (and winning) relate to nearby housing markets? Public data only.

## Data sources
| Need | Source |
|---|---|
| Home values by ZIP | Zillow Research ZHVI (`files.zillowstatic.com`) |
| ZIP centroids | US Census 2020 ZCTA Gazetteer (`www2.census.gov`) |
| Venues | `data/seed/venues.csv` (hand-curated; coordinates **unverified**, to be checked against OSM/Wikidata) |

## Method
For each venue, ZIPs within 3 miles are the treated area. A **synthetic twin** is a convex blend of ZIPs
from elsewhere (none within 15 miles) fitted to the treated area's home-value path over the 60 months
before opening. The post-opening gap (months 25-36) is the estimate. Inference is by **in-space placebos**:
the same procedure on random geographic clusters with no venue (p = share at least as extreme).
A **density-matched** re-run (donors limited to similar ZIP land area) is a sensitivity check.

Verdicts: *signal* (placebo p <= 0.05, enough history), *suggestive*, *inconclusive*,
*pandemic-confounded* (opened 2019+), *no data* (Zillow starts in 2000; too little pre-period).

Calibration (simulation, 25 null worlds): placebo false-positive rate 4% at nominal 10%.
Pre-periods under 60 months were biased by roughly -2 points in simulation, hence the 60-month default.

## Current findings (read the caveats)
Only **Barclays Center** (+31.7%, placebo p = 0.024) is flagged; with density-matched donors it is
+18.1% (p = 0.098), so the size depends on the comparison pool and Brooklyn's wider redevelopment
is not separated out. Chase Center's -18.6% is flagged **pandemic-confounded**, not a stadium effect.
Everything else is inconclusive. An earlier difference-in-differences with a suburban control ring
produced several large "effects" that disappeared under the synthetic control.

## Usage
```
pip install -e ".[dev]"
atlas fetch                          # download Zillow + Census data to data/raw
atlas synth                          # synthetic-control table for all venues
atlas export --out web/public/data   # JSON for the web app (about 20 min)
cd web && npm install && npm run dev
```

### Ask the data (Claude-powered)
`atlas serve` serves the built app (`cd web && npm run build` first) plus `POST /api/ask`. Questions are
answered by `claude-opus-5-5` from a compact table of the exported results only (structured output,
low effort), told to respect each venue's verdict and caveats and never to claim causation. It needs
credentials (`ANTHROPIC_API_KEY` or `ant auth login`); without them the box says so. Server-side
refusal fallback (`fallbacks: "default"`) is enabled, requests are length-limited, and the endpoint is
rate-limited to 10 questions/minute per client. A static host (e.g. GitHub Pages) shows the app but not
the question box.

## Roadmap
1. ~~Pipeline, DiD, synthetic control, placebo inference, verification, 3D web app~~
2. Pandemic-robust comparison for 2019-20 venues (urban-core donors from census density)
3. ~~Natural-language query layer~~ (built; not yet exercised against the live API)
4. More leagues, NBA/NHL venues, team success overlays (championships)
