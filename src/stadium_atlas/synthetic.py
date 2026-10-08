"""Synthetic-control estimate of a venue's effect on nearby home values.

The treated unit is the mean log value of ZIPs near the venue. The counterfactual is a convex
blend of donor ZIPs (far from the venue) chosen to match the treated unit's pre-opening path.
Inference is by in-space placebos: the same procedure on random geographic clusters that have
no venue, so the estimate is judged against how big "effects" get by chance.

Series are demeaned on the pre-period, so we match dynamics (trend/shape), not price level.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .geo import haversine_miles

# Short pre-periods let slow housing cycles masquerade as trend and bias the counterfactual
# (in simulation: ~-2 pts of bias at 36 months, ~-0.4 at 60), so default long and flag short.
DEFAULT_PRE_MONTHS = 60
MIN_PRE_MONTHS = 36


def prepare_wide(zhvi: pd.DataFrame) -> pd.DataFrame:
    """Long ZHVI -> months x zips matrix of log values."""
    d = zhvi.assign(period=zhvi["date"].dt.to_period("M"), lv=np.log(zhvi["value"]))
    return d.pivot(index="period", columns="zip", values="lv")


def fit_weights(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Non-negative weights summing to 1 minimising ||y - Xw||^2."""
    k = X.shape[1]
    w0 = np.full(k, 1.0 / k)
    res = minimize(
        lambda w: float(np.sum((y - X @ w) ** 2)), w0,
        jac=lambda w: -2 * X.T @ (y - X @ w),
        bounds=[(0.0, 1.0)] * k,
        constraints={"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones(k)},
        method="SLSQP", options={"maxiter": 200, "ftol": 1e-10},
    )
    w = np.clip(res.x, 0, None)
    return w / w.sum()


@dataclass
class SCResult:
    effect_pct: float
    pre_rmspe: float           # pre-period fit error (log points); small = credible counterfactual
    post_rmspe: float
    gap: pd.Series             # relative month -> treated minus synthetic (log points)
    weights: pd.Series         # donor zip -> weight (non-zero only)
    n_treated: int
    n_donors: int
    p_value: float | None = None
    n_placebos: int = 0
    treated_path: pd.Series | None = None    # rel month -> demeaned log value of treated unit
    synthetic_path: pd.Series | None = None  # rel month -> demeaned log value of counterfactual

    def as_dict(self) -> dict:
        return {"effect_pct": self.effect_pct, "pre_rmspe": self.pre_rmspe,
                "post_rmspe": self.post_rmspe, "n_treated": self.n_treated,
                "n_donors": self.n_donors, "p_value": self.p_value,
                "n_placebos": self.n_placebos}


def _window(wide: pd.DataFrame, event_date, pre_months: int, post_months: int):
    ev = pd.Period(event_date, "M")
    rel = np.array([(p - ev).n for p in wide.index])
    mask = (rel >= -pre_months) & (rel <= post_months)
    sub = wide.loc[mask]
    return sub, rel[mask], sub.columns[sub.notna().all()]


def synthetic_control(wide: pd.DataFrame, treated_zips, event_date, pre_months: int = DEFAULT_PRE_MONTHS,
                      post_months: int = 36, exclude_zips=(), top_k: int = 100) -> SCResult:
    sub, rel, complete = _window(wide, event_date, pre_months, post_months)
    treated = [z for z in treated_zips if z in set(complete)]
    if len(treated) < 2:
        raise ValueError("need at least 2 treated ZIPs with complete data")
    banned = set(exclude_zips) | set(treated)
    donors = [z for z in complete if z not in banned]
    if len(donors) < 10:
        raise ValueError("donor pool too small")

    pre = rel < 0
    A = sub[donors].to_numpy()
    y = sub[treated].to_numpy().mean(axis=1)
    A = A - A[pre].mean(axis=0)
    y = y - y[pre].mean()

    rmse = np.sqrt(((A[pre] - y[pre, None]) ** 2).mean(axis=0))
    keep = np.argsort(rmse)[:top_k]
    w = fit_weights(A[pre][:, keep], y[pre])
    gap = y - A[:, keep] @ w

    eff = (rel >= post_months - 11) & (rel <= post_months)
    nz = w > 1e-4
    return SCResult(
        effect_pct=float((np.exp(gap[eff].mean()) - 1) * 100),
        pre_rmspe=float(np.sqrt((gap[pre] ** 2).mean())),
        post_rmspe=float(np.sqrt((gap[rel >= 0] ** 2).mean())),
        gap=pd.Series(gap, index=rel, name="gap"),
        weights=pd.Series(w[nz], index=np.array(donors)[keep][nz]).sort_values(ascending=False),
        n_treated=len(treated), n_donors=len(donors),
        treated_path=pd.Series(y, index=rel), synthetic_path=pd.Series(y - gap, index=rel),
    )


def placebo_test(wide: pd.DataFrame, zctas: pd.DataFrame, result: SCResult, event_date,
                 exclude_zips=(), pre_months: int = DEFAULT_PRE_MONTHS, post_months: int = 36,
                 n_placebo: int = 40, seed: int = 0, exclusion_mi: float = 15.0,
                 fit_tolerance: float | None = None) -> SCResult:
    """Attach a placebo p-value: how often a venue-less cluster shows an effect this large.

    Placebo clusters are the `n_treated` nearest ZIPs to a random center. Two-sided
    p = (1 + #{|placebo| >= |effect|}) / (1 + n_used).

    `fit_tolerance` optionally drops placebos whose pre-fit exceeds that multiple of the real
    unit's. It is off by default: in simulation it made p-values anti-conservative (24% false
    positives at a nominal 10%, vs. 4% without it) because a very tight real fit discards
    legitimate placebos.
    """
    _, _, complete = _window(wide, event_date, pre_months, post_months)
    pool = [z for z in complete if z not in set(exclude_zips)]
    geo = zctas.drop_duplicates("zip").set_index("zip").reindex(pool).dropna(subset=["lat", "lon"])
    pool = list(geo.index)
    lat, lon = geo["lat"].to_numpy(), geo["lon"].to_numpy()

    rng = np.random.default_rng(seed)
    effects: list[float] = []
    for c in rng.choice(len(pool), size=min(n_placebo * 2, len(pool)), replace=False):
        if len(effects) >= n_placebo:
            break
        d = haversine_miles(lat[c], lon[c], lat, lon)
        cluster = [pool[i] for i in np.argsort(d)[: result.n_treated]]
        # never let the real treated area (or its surroundings) donate to a placebo
        nearby = [pool[i] for i in np.where(d < exclusion_mi)[0]] + list(exclude_zips)
        try:
            r = synthetic_control(wide, cluster, event_date, pre_months, post_months, nearby)
        except ValueError:
            continue
        if fit_tolerance is None or r.pre_rmspe <= fit_tolerance * max(result.pre_rmspe, 1e-6):
            effects.append(r.effect_pct)

    arr = np.abs(np.array(effects))
    result.n_placebos = len(effects)
    result.p_value = float((1 + (arr >= abs(result.effect_pct)).sum()) / (1 + len(effects)))
    return result
