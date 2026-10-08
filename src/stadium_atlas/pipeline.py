"""Join venues, ZIP centroids and ZHVI into per-venue analysis panels."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .analysis import EffectEstimate, did_effect, event_study
from .geo import DEFAULT_RINGS, assign_rings, haversine_miles
from .robustness import robustness_grid, summarize
from .synthetic import DEFAULT_PRE_MONTHS as SC_PRE
from .synthetic import MIN_PRE_MONTHS as SC_MIN_PRE
from .synthetic import SCResult, _window, placebo_test, synthetic_control

DEFAULT_PRE_MONTHS = 36
MIN_PRE_MONTHS = 24
SEED_VENUES = Path(__file__).resolve().parents[2] / "data" / "seed" / "venues.csv"


# Typical season-opening month, used only when Wikidata has a year but no precise date.
DEFAULT_OPENING_MONTH = {"MLB": 4, "NFL": 9, "NBA": 10, "NHL": 10}


def opening_month(venue: pd.Series) -> int:
    m = venue.get("opened_month")
    if m is not None and not pd.isna(m):
        return int(m)
    return DEFAULT_OPENING_MONTH.get(venue.get("league"), 4)


def load_venues(path: Path = SEED_VENUES) -> pd.DataFrame:
    return pd.read_csv(path)


def venue_panel(venue: pd.Series, zctas: pd.DataFrame, zhvi: pd.DataFrame,
                rings=DEFAULT_RINGS) -> pd.DataFrame:
    """ZIP-month panel (zip, date, value, ring, distance_mi) for one venue."""
    near = assign_rings(zctas, venue["lat"], venue["lon"], rings)
    return zhvi.merge(near[["zip", "ring", "distance_mi"]], on="zip", how="inner")


def venue_effect(venue: pd.Series, zctas: pd.DataFrame, zhvi: pd.DataFrame,
                 month: int | None = None, **kwargs) -> tuple[EffectEstimate, pd.DataFrame]:
    panel = venue_panel(venue, zctas, zhvi)
    event_date = pd.Timestamp(year=int(venue["opened_year"]),
                              month=month or opening_month(venue), day=1)
    first = zhvi["date"].min()
    available = (event_date.year - first.year) * 12 + (event_date.month - first.month)
    pre = min(kwargs.pop("pre_months", DEFAULT_PRE_MONTHS), available)
    if pre < MIN_PRE_MONTHS:
        raise ValueError(f"insufficient pre-period: only {available} months of history "
                         f"before opening (need {MIN_PRE_MONTHS})")
    return did_effect(panel, event_date, pre_months=pre, **kwargs), event_study(panel, event_date)


MIN_TREATED_ZIPS = 5
RADIUS_LADDER = (3.0, 5.0, 7.0)   # widen the treated area when too few ZIPs have complete data
DENSE_RATIO = 3.0                 # "similar land area": within this factor of the treated median


def venue_synthetic(venue: pd.Series, zctas: pd.DataFrame, wide: pd.DataFrame,
                    month: int | None = None, treated_radius_mi: float | None = None,
                    exclusion_mi: float = 15.0, n_placebo: int = 40, post_months: int = 36,
                    density_match: float | None = None, grid: bool = False
                    ) -> tuple[SCResult, dict]:
    """Synthetic-control estimate with placebo p-values for one venue.

    Treated = ZIPs within the treated radius (3 mi, widened to 5 then 7 if fewer than
    MIN_TREATED_ZIPS have complete data, unless a radius is forced); everything within
    `exclusion_mi` is barred from the donor pool. Besides the usual placebo p-value, a second one
    draws placebos only from ZIPs of similar land area. With `grid`, the robustness specification
    grid is computed too. Returns (result, meta).
    """
    event_date = pd.Timestamp(year=int(venue["opened_year"]),
                              month=month or opening_month(venue), day=1)
    first = wide.index.min()
    available = (event_date.year - first.year) * 12 + (event_date.month - first.month)
    pre = min(SC_PRE, available)
    if pre < SC_MIN_PRE:
        raise ValueError(f"insufficient pre-period: only {available} months of history "
                         f"before opening (need {SC_MIN_PRE})")
    d = haversine_miles(venue["lat"], venue["lon"], zctas["lat"].to_numpy(), zctas["lon"].to_numpy())
    _, _, complete = _window(wide, event_date, pre, post_months)
    have = set(complete)
    radii = (treated_radius_mi,) if treated_radius_mi else RADIUS_LADDER
    for radius in radii:
        treated = [z for z in zctas.loc[d < radius, "zip"] if z in have]
        if len(treated) >= MIN_TREATED_ZIPS:
            break
    excluded = list(zctas.loc[d < exclusion_mi, "zip"])
    if density_match and "land_sqmi" in zctas:
        # Urban cores and suburbs diverged after 2020, so only borrow from ZIPs of similar land
        # area (a cheap density proxy): at most `density_match` x the treated median.
        cap = density_match * zctas.loc[zctas["zip"].isin(treated), "land_sqmi"].median()
        excluded = excluded + list(zctas.loc[zctas["land_sqmi"] > cap, "zip"])
    res = synthetic_control(wide, treated, event_date, pre_months=pre, post_months=post_months,
                            exclude_zips=excluded)
    dense_pool = None
    if "land_sqmi" in zctas:
        med = zctas.loc[zctas["zip"].isin(treated), "land_sqmi"].median()
        dense_pool = list(zctas.loc[zctas["land_sqmi"].between(med / DENSE_RATIO, med * DENSE_RATIO),
                                    "zip"])
    res = placebo_test(wide, zctas, res, event_date, exclude_zips=excluded, pre_months=pre,
                       post_months=post_months, n_placebo=n_placebo, exclusion_mi=exclusion_mi,
                       dense_pool=dense_pool)
    meta = {"pre_months": pre, "low_confidence": pre < SC_PRE, "treated_radius": radius,
            "density_matched": bool(density_match)}
    if grid:
        rows = robustness_grid(wide, zctas, d, event_date, pre, excluded, res, radius, post_months)
        meta["grid"] = rows
        meta["grid_summary"] = summarize(rows, res.effect_pct)
    return res, meta
