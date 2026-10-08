# Stadium Effect Atlas

How do pro sports venues (and winning) relate to nearby housing markets? Public data only.

## Data sources
| Need | Source |
|---|---|
| Home values by ZIP | Zillow Research ZHVI (`files.zillowstatic.com`) |
| ZIP centroids | US Census 2020 ZCTA Gazetteer (`www2.census.gov`) |
| Venues | `data/seed/venues.csv` (hand-curated; coordinates **unverified**, to be checked against OSM/Wikidata) |

## Method
For each venue, ZIPs within 3 miles are the treated area (widened to 5, then 7 miles when fewer than 5
have complete data). A **synthetic twin** is a convex blend of ZIPs from elsewhere (none within 15 miles)
fitted to the treated area's home-value path over up to 60 months before opening. The post-opening gap
(months 25-36) is the estimate.

Inference and checks:
- **Placebo p-value**: the same procedure on random geographic clusters with no venue. A second p-value
  draws placebos only from ZIPs of similar land area ("dense-area placebo").
- **Robustness grid**: radius (1.5/3/5 mi) x post-window (12/24/36 mo) plus dropping each of the top 3
  donors; a result that flips sign in more than 25% of setups is downgraded.
- **Density-matched donor re-run** as a sensitivity check.
- **Pooled estimate** across venues: mean with a t-interval over venues, a random-effects model, and a
  pooled placebo test (venue effects vs. draws of one placebo per venue). Venues opened 2019-20 are kept out
  of the pool (pandemic window); league and opening-era breakdowns are exploratory.

Verdicts: *distinct* (placebo p <= 0.05, >= 60 months of history, survives the checks), *suggestive*,
*inconclusive*, *pandemic-confounded* (opened 2019+), *no data* (Zillow starts in 2000).

Calibration (simulation): venue-level placebo false-positive rate is about 4% at a nominal 10%; the pooled
placebo p is slightly liberal (about 6% at a nominal 5%), so the headline interval is a t-interval (95%
coverage). Pre-periods under 60 months were biased by roughly -2 points, hence the 60-month default.

## Current findings (read the caveats)
37 venues (MLB/NFL/NBA/NHL, opened 2000-2020; locations and opening dates verified against Wikidata); 34 can be
scored. Two stand out individually (**Barclays Center +31.5%**, **Fiserv Forum +14.9%**), five are
suggestive, 23 inconclusive, four are pandemic-confounded, three cannot be scored.

**Pooled (30 venues opened 2003-2018): +3.7% average, 95% CI -0.2% to +7.8%** (random effects +4.7%, +0.9% to
+8.6%; pooled placebo p = 0.009). The tests agree on direction but not certainty, and venues differ a lot
(I-squared 59%; 19 of 30 positive, sign test p = 0.20). By opening era: 2003-07 -1.3% (-8.5 to +6.5),
2008-11 +3.4% (-1.8 to +8.8), 2012-18 +9.7% (+2.2 to +17.8). By league (exploratory): NBA +9.4%, NHL +6.4%,
MLB +1.1%, NFL +0.1%.

Read with care: this is an association, not causation. Stadiums are usually built inside larger redevelopment,
which the method cannot separate; venues opened 2006-09 had post-windows in the housing bust; the two Glendale,
AZ venues have opposite signs (+20% and -19%), a sign that metro-level shocks can swamp venue effects.
Chase Center's -20.2% is labelled pandemic-confounded (similarly sized ZIPs show an effect that large about 7%
of the time, so the pandemic is a likely but not proven explanation). The first difference-in-differences with
a suburban control ring produced several large "effects" that disappeared under the synthetic control.

## Usage
```
pip install -e ".[dev]"
atlas fetch                          # Zillow + Census data into data/raw (about 125 MB)
atlas export --out web/public/data   # estimates for all venues (about 7 min on 4 cores)
atlas geo                            # simplified ZIP/state boundaries (needs the two Census boundary zips)
atlas titles                         # MLB World Series winners for the title markers
atlas pool                           # recompute pooled.json from saved placebo draws
cd web && npm install && npm run dev
```
`atlas geo` also needs `cb_2020_us_zcta520_500k.zip` and `cb_2020_us_state_20m.zip` from
`https://www2.census.gov/geo/tiger/GENZ2020/shp/` in `data/raw/`.

The app has a "Big picture" view, per-venue robustness strips, venue comparison, find-your-ZIP, shareable
links (`?venue=barclays&t=26`) and, on the Python server, a question box.

### Ask the data (Claude-powered)
`atlas serve` serves the built app (`cd web && npm run build` first) plus `POST /api/ask`. Questions are
answered by `claude-opus-5-5` from a compact table of the exported results only (structured output,
low effort), told to respect each venue's verdict and caveats and never to claim causation. It needs
credentials (`ANTHROPIC_API_KEY` or `ant auth login`); without them the box says so. Server-side
refusal fallback (`fallbacks: "default"`) is enabled, requests are length-limited, and the endpoint is
rate-limited to 10 questions/minute per client. A static host (e.g. GitHub Pages) shows the app but not
the question box. The Q&A path has been tested with a stub client only, not against the live API.

Deployed from `main` to GitHub Pages by `.github/workflows/pages.yml`.

## Roadmap
1. Pandemic-robust comparison for 2019-20 venues using real population density (needs a free Census API key)
2. Live test of the question box against the API
3. Championship overlay beyond MLB (no reliable public results API on an allowed host so far)
4. More venues (MLS, college), and recession-robust comparison for 2006-09 venues
