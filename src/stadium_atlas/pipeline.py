"""Join venues, ZIP centroids and ZHVI into per-venue analysis panels."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .analysis import EffectEstimate, did_effect, event_study
from .geo import DEFAULT_RINGS, assign_rings

DEFAULT_PRE_MONTHS = 36
MIN_PRE_MONTHS = 24
SEED_VENUES = Path(__file__).resolve().parents[2] / "data" / "seed" / "venues.csv"


def load_venues(path: Path = SEED_VENUES) -> pd.DataFrame:
    return pd.read_csv(path)


def venue_panel(venue: pd.Series, zctas: pd.DataFrame, zhvi: pd.DataFrame,
                rings=DEFAULT_RINGS) -> pd.DataFrame:
    """ZIP-month panel (zip, date, value, ring, distance_mi) for one venue."""
    near = assign_rings(zctas, venue["lat"], venue["lon"], rings)
    return zhvi.merge(near[["zip", "ring", "distance_mi"]], on="zip", how="inner")


def venue_effect(venue: pd.Series, zctas: pd.DataFrame, zhvi: pd.DataFrame,
                 opening_month: int = 4, **kwargs) -> tuple[EffectEstimate, pd.DataFrame]:
    panel = venue_panel(venue, zctas, zhvi)
    event_date = pd.Timestamp(year=int(venue["opened_year"]), month=opening_month, day=1)
    first = zhvi["date"].min()
    available = (event_date.year - first.year) * 12 + (event_date.month - first.month)
    pre = min(kwargs.pop("pre_months", DEFAULT_PRE_MONTHS), available)
    if pre < MIN_PRE_MONTHS:
        raise ValueError(f"insufficient pre-period: only {available} months of history "
                         f"before opening (need {MIN_PRE_MONTHS})")
    return did_effect(panel, event_date, pre_months=pre, **kwargs), event_study(panel, event_date)
