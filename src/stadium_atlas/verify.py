"""Cross-check seeded venues (coordinates, opening year) against Wikidata."""
from __future__ import annotations

import re
import time

import pandas as pd
import requests

from .geo import haversine_miles

SPARQL_URL = "https://query.wikidata.org/sparql"
UA = "stadium-atlas/0.1 (public-data research project)"

QUERY = """
SELECT ?item ?coord ?opened ?inception WHERE {{
  ?item rdfs:label "{name}"@en ; wdt:P625 ?coord .
  VALUES ?cls {{ wd:Q483110 wd:Q641226 wd:Q1076486 }}
  ?item wdt:P31/wdt:P279* ?cls .
  OPTIONAL {{ ?item wdt:P1619 ?opened }}
  OPTIONAL {{ ?item wdt:P571 ?inception }}
}} LIMIT 5
"""
_POINT = re.compile(r"Point\(([-\d.]+) ([-\d.]+)\)")


def parse_point(wkt: str) -> tuple[float, float]:
    """WKT 'Point(lon lat)' -> (lat, lon)."""
    m = _POINT.search(wkt)
    if not m:
        raise ValueError(f"unparseable coordinate: {wkt!r}")
    return float(m.group(2)), float(m.group(1))


def lookup(name: str, timeout: int = 60) -> list[dict]:
    q = QUERY.format(name=name.replace('"', '\\"'))
    for attempt in range(4):
        r = requests.get(SPARQL_URL, params={"query": q, "format": "json"},
                         headers={"User-Agent": UA}, timeout=timeout)
        if r.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(2 ** (attempt + 1))
    r.raise_for_status()
    out = []
    for b in r.json()["results"]["bindings"]:
        lat, lon = parse_point(b["coord"]["value"])
        date = b.get("opened", b.get("inception", {})).get("value")
        out.append({"qid": b["item"]["value"].rsplit("/", 1)[-1], "lat": lat, "lon": lon,
                    "year": int(date[:4]) if date else None, "date": date})
    return out


def verify(venues: pd.DataFrame) -> pd.DataFrame:
    """One row per venue: seed vs. Wikidata coords/year, with discrepancies."""
    rows = []
    for _, v in venues.iterrows():
        try:
            hits = lookup(v["name"])
        except requests.RequestException as e:
            rows.append({"venue_id": v["venue_id"], "status": f"error: {e}"})
            continue
        if not hits:
            rows.append({"venue_id": v["venue_id"], "status": "not found"})
            continue
        h = min(hits, key=lambda h: haversine_miles(v["lat"], v["lon"], h["lat"], h["lon"]))
        dist = float(haversine_miles(v["lat"], v["lon"], h["lat"], h["lon"]))
        rows.append({
            "venue_id": v["venue_id"], "qid": h["qid"], "wd_lat": h["lat"], "wd_lon": h["lon"],
            "dist_mi": round(dist, 3), "seed_year": v["opened_year"], "wd_year": h["year"],
            "status": "ok" if dist < 0.5 and h["year"] in (None, v["opened_year"]) else "REVIEW",
        })
    return pd.DataFrame(rows)


def opening_month(date: str | None) -> int | None:
    """Month from a Wikidata datetime, or None when it looks like a year-only date (Jan 1)."""
    if not date:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", date)
    if not m or (m.group(2) == "01" and m.group(3) == "01"):
        return None
    return int(m.group(2))


def resolve(names: list[str], expected_year: int, near: tuple[float, float],
            max_mi: float = 30.0) -> dict | None:
    """Best Wikidata match for any alias: within `max_mi` of `near`, preferring the expected year."""
    best = None
    for name in names:
        for h in lookup(name):
            d = float(haversine_miles(near[0], near[1], h["lat"], h["lon"]))
            if d > max_mi:
                continue
            score = (h["year"] != expected_year, d)   # year match first, then proximity
            if best is None or score < best[0]:
                best = (score, {**h, "alias": name, "dist_to_city_mi": round(d, 1)})
        time.sleep(1.0)  # be polite to the public endpoint
    return best[1] if best else None


QID_QUERY = """
SELECT ?coord ?opened ?inception WHERE {{
  wd:{qid} wdt:P625 ?coord .
  OPTIONAL {{ wd:{qid} wdt:P1619 ?opened }}
  OPTIONAL {{ wd:{qid} wdt:P571 ?inception }}
}} LIMIT 1
"""


def lookup_qid(qid: str, timeout: int = 60) -> dict | None:
    """Coordinates and opening date for a known Wikidata item."""
    for attempt in range(4):
        r = requests.get(SPARQL_URL, params={"query": QID_QUERY.format(qid=qid), "format": "json"},
                         headers={"User-Agent": UA}, timeout=timeout)
        if r.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(2 ** (attempt + 1))
    r.raise_for_status()
    rows = r.json()["results"]["bindings"]
    if not rows:
        return None
    b = rows[0]
    lat, lon = parse_point(b["coord"]["value"])
    date = b.get("opened", b.get("inception", {})).get("value")
    return {"qid": qid, "lat": lat, "lon": lon, "year": int(date[:4]) if date else None, "date": date}
