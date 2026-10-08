"""Specification grid: does a venue's estimate survive reasonable analyst choices?

Varies the treated radius, the post-opening window, and leave-one-out removal of the donors the
counterfactual leans on most. Only point estimates are recomputed (no placebos), so it is cheap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .synthetic import SCResult, synthetic_control

RADII = (1.5, 3.0, 5.0)
WINDOWS = (12, 24, 36)       # months after opening; effect = mean gap over the last 12 of them
LOO_TOP = 3


def robustness_grid(wide: pd.DataFrame, zctas: pd.DataFrame, dist: np.ndarray, event_date,
                    pre_months: int, exclude_zips, primary: SCResult, primary_radius: float,
                    primary_window: int = 36) -> list[dict]:
    """One row per specification: radius x window, plus leave-one-out of the top donors."""
    rows: list[dict] = []

    def run(spec, treated, window, extra_exclude=()):
        try:
            r = synthetic_control(wide, treated, event_date, pre_months=pre_months,
                                  post_months=window, exclude_zips=list(exclude_zips) + list(extra_exclude))
        except ValueError:
            return
        rows.append({"spec": spec, "effect_pct": round(r.effect_pct, 2), "n_treated": r.n_treated,
                     "pre_rmspe": round(r.pre_rmspe, 4)})

    for radius in RADII:
        treated = list(zctas.loc[dist < radius, "zip"])
        for window in WINDOWS:
            run(f"{radius:g} mi, {window} mo", treated, window)

    primary_treated = list(zctas.loc[dist < primary_radius, "zip"])
    for i, donor in enumerate(primary.weights.head(LOO_TOP).index, start=1):
        run(f"drop donor #{i}", primary_treated, primary_window, [donor])
    return rows


def summarize(rows: list[dict], primary_effect: float) -> dict:
    """Agreement statistics for the grid, relative to the primary estimate."""
    if not rows:
        return {"n": 0}
    eff = np.array([r["effect_pct"] for r in rows])
    same = np.sign(eff) == np.sign(primary_effect)
    return {"n": len(rows), "share_same_sign": round(float(same.mean()), 3),
            "median": round(float(np.median(eff)), 2), "min": round(float(eff.min()), 2),
            "max": round(float(eff.max()), 2)}
