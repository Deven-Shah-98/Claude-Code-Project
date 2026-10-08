"""Event-study and difference-in-differences estimates for a venue's surrounding ZIPs.

Input panel columns: zip, date, value, ring. Rings named "control" form the comparison group;
every other ring is treated unless `treated_rings` says otherwise.

Caveat: this is an association, not proof of causation. Stadiums are often built where
redevelopment is already planned, so the result also reports a pre-trend diagnostic.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

CONTROL = "control"


def _months_between(dates: pd.Series, event_date: pd.Timestamp) -> pd.Series:
    return (dates.dt.year - event_date.year) * 12 + (dates.dt.month - event_date.month)


def _prepare(panel: pd.DataFrame, event_date) -> pd.DataFrame:
    event_date = pd.Timestamp(event_date)
    df = panel.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["rel_month"] = _months_between(df["date"], event_date)
    df["log_value"] = np.log(df["value"])
    return df


def event_study(panel: pd.DataFrame, event_date, window: tuple[int, int] = (-60, 60),
                baseline: tuple[int, int] = (-12, -1)) -> pd.DataFrame:
    """Mean log change vs. each ZIP's pre-event baseline, by ring and relative month.

    Returns ring, rel_month, mean_log_change, gap_vs_control (log points; ~ fraction change).
    """
    df = _prepare(panel, event_date)
    base = (df[df["rel_month"].between(*baseline)].groupby("zip")["log_value"].mean()
            .rename("baseline"))
    df = df.join(base, on="zip").dropna(subset=["baseline"])
    df = df[df["rel_month"].between(*window)]
    df["log_change"] = df["log_value"] - df["baseline"]
    out = (df.groupby(["ring", "rel_month"])["log_change"].mean()
           .rename("mean_log_change").reset_index())
    ctrl = (out[out["ring"] == CONTROL].set_index("rel_month")["mean_log_change"]
            .rename("control_change"))
    out = out.join(ctrl, on="rel_month")
    out["gap_vs_control"] = out["mean_log_change"] - out["control_change"]
    return out.drop(columns="control_change")


@dataclass
class EffectEstimate:
    effect_pct: float          # percent difference in growth vs. control
    ci_low_pct: float
    ci_high_pct: float
    n_treated: int
    n_control: int
    pretrend_pct_per_year: float  # treated minus control drift before the event (should be ~0)
    significant: bool

    def as_dict(self) -> dict:
        return asdict(self)


def did_effect(panel: pd.DataFrame, event_date, pre_months: int = 36, post_months: int = 36,
               treated_rings: list[str] | None = None, n_boot: int = 2000, seed: int = 0,
               min_obs_frac: float = 0.8) -> EffectEstimate:
    """Difference-in-differences on mean log values, bootstrap CI resampling ZIPs.

    Compares the average of the final 12 months of the post window to the average of the
    `pre_months` before the event. ZIPs missing too much data in either window are dropped.
    """
    df = _prepare(panel, event_date)
    pre = df[df["rel_month"].between(-pre_months, -1)]
    post = df[df["rel_month"].between(post_months - 11, post_months)]

    ok = (pre.groupby("zip").size() >= min_obs_frac * pre_months) & \
         (post.groupby("zip").size() >= min_obs_frac * 12)
    zips = ok[ok].index
    pre, post = pre[pre["zip"].isin(zips)], post[post["zip"].isin(zips)]

    ring = df.drop_duplicates("zip").set_index("zip")["ring"].loc[zips]
    is_treated = ring.isin(treated_rings) if treated_rings else ring != CONTROL
    is_control = ring == CONTROL
    if is_treated.sum() < 2 or is_control.sum() < 2:
        raise ValueError("need at least 2 treated and 2 control ZIPs with sufficient data")

    delta = post.groupby("zip")["log_value"].mean() - pre.groupby("zip")["log_value"].mean()
    delta = delta.loc[zips]

    def slope(g: pd.DataFrame) -> float:
        return np.polyfit(g["rel_month"], g["log_value"], 1)[0] * 12

    slopes = pre.groupby("zip").apply(slope, include_groups=False).loc[zips]

    t, c = delta[is_treated], delta[is_control]
    point = t.mean() - c.mean()

    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    tv, cv = t.to_numpy(), c.to_numpy()
    for i in range(n_boot):
        boots[i] = rng.choice(tv, len(tv)).mean() - rng.choice(cv, len(cv)).mean()
    lo, hi = np.percentile(boots, [2.5, 97.5])

    pct = lambda x: float((np.exp(x) - 1) * 100)
    return EffectEstimate(
        effect_pct=pct(point), ci_low_pct=pct(lo), ci_high_pct=pct(hi),
        n_treated=int(is_treated.sum()), n_control=int(is_control.sum()),
        pretrend_pct_per_year=pct(slopes[is_treated].mean() - slopes[is_control].mean()),
        significant=bool(lo > 0 or hi < 0),
    )
