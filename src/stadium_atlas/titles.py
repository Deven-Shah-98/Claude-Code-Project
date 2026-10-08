"""World Series champions from MLB's official Stats API, mapped to MLB venues.

Only MLB is covered: it is the one league here with a reliable public results API on an allowed
host. Output `titles.json` maps venue_id -> ["YYYY-MM", ...] for each title won by that venue's team.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from . import pipeline

API = "https://statsapi.mlb.com/api/v1/schedule"


def world_series_winner(season: int, timeout: int = 40) -> tuple[str, str] | None:
    """(team name, 'YYYY-MM' of the clinching game) for a season, or None if not found."""
    params = {"sportId": 1, "gameType": "W", "season": season, "hydrate": "team",
              "startDate": f"{season}-09-25", "endDate": f"{season}-11-20"}
    for attempt in range(3):
        r = requests.get(API, params=params, timeout=timeout)
        if r.status_code == 200:
            break
        time.sleep(2 * (attempt + 1))
    else:
        return None
    games = [g for day in r.json().get("dates", []) for g in day["games"]]
    if not games:
        return None
    last = max(games, key=lambda g: g["gameDate"])
    for side in ("home", "away"):
        if last["teams"][side].get("isWinner"):
            return last["teams"][side]["team"]["name"], last["officialDate"][:7]
    return None


def export_titles(out_dir: str = "web/public/data", first: int = 2000, last: int = 2025) -> dict:
    champs = {s: world_series_winner(s) for s in range(first, last + 1)}
    venues = pipeline.load_venues()
    out: dict[str, list[str]] = {}
    for _, v in venues[venues["league"] == "MLB"].iterrows():
        won = sorted(d for c in champs.values() if c and c[0] == v["team"] for d in [c[1]])
        out[v["venue_id"]] = won
    Path(out_dir, "titles.json").write_text(json.dumps(out, separators=(",", ":")))
    return {"seasons_found": sum(c is not None for c in champs.values()), "titles": out}
