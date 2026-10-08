"""Export per-venue results and ZIP time series as static JSON for the web app."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import pipeline
from .geo import haversine_miles
from .synthetic import SCResult, prepare_wide

PANDEMIC_START_YEAR = 2019   # post-windows for venues opening from here include 2020-22
FEW_ZIPS = 5
MAP_RADIUS_MI = 15.0
ROBUST_DENSITY = 3.0       # donor land area cap (x treated median) for the robustness re-run
ROBUST_MIN_DONORS = 200    # below this the robustness pool is too thin to judge anything


def verdict(res: SCResult | None, meta: dict | None, opened_year: int) -> tuple[str, list[str]]:
    """Honest label + caveats. Order matters: data problems > pandemic > significance."""
    if res is None:
        return "no-data", ["Not enough pre-opening or ZIP-level data to estimate."]
    caveats = []
    if meta["low_confidence"]:
        caveats.append(f"Only {meta['pre_months']} months of pre-opening history (60 preferred).")
    if res.n_treated < FEW_ZIPS:
        caveats.append(f"Only {res.n_treated} ZIP codes in the treated area.")
    pandemic = opened_year >= PANDEMIC_START_YEAR
    if pandemic:
        caveats.append("Post-opening window overlaps the 2020-22 pandemic shift between urban "
                       "cores and suburbs.")
    if pandemic:
        return "confounded", caveats
    if res.p_value is not None and res.p_value <= 0.05 and not meta["low_confidence"]:
        return "signal", caveats
    if res.p_value is not None and res.p_value <= 0.10:
        return "suggestive", caveats
    return "inconclusive", caveats


def robustness_downgrade(primary: SCResult, alt: SCResult) -> str | None:
    """Reason to distrust the primary estimate, or None if the alternative donor pool agrees."""
    if alt.n_donors < ROBUST_MIN_DONORS:
        return None
    same_sign = np.sign(alt.effect_pct) == np.sign(primary.effect_pct)
    if same_sign and alt.p_value is not None and alt.p_value <= 0.10:
        return None
    return (f"Sensitive to the comparison pool: with density-matched donors the estimate is "
            f"{alt.effect_pct:+.1f}% (placebo p = {alt.p_value:.2f}).")


def _quarter_idx(wide: pd.DataFrame, start: pd.Period, end: pd.Period) -> list[pd.Period]:
    periods = [p for p in wide.index if start <= p <= end and p.month in (3, 6, 9, 12)]
    return periods


def zip_series(venue: pd.Series, zctas: pd.DataFrame, wide: pd.DataFrame,
               month: int | None = None, years_before: int = 5, years_after: int = 3) -> dict:
    """Quarterly ZIP panel within MAP_RADIUS_MI: value ($k) and % change vs pre-opening level."""
    opened = pd.Period(year=int(venue["opened_year"]), month=month or pipeline.opening_month(venue), freq="M")
    qs = _quarter_idx(wide, opened - 12 * years_before, opened + 12 * years_after)
    d = haversine_miles(venue["lat"], venue["lon"], zctas["lat"].to_numpy(), zctas["lon"].to_numpy())
    near = zctas.assign(dist=d)[d < MAP_RADIUS_MI]
    near = near[near["zip"].isin(wide.columns)]
    base_idx = [p for p in wide.index if opened - 12 <= p < opened]
    out_zips = []
    for _, z in near.sort_values("dist").iterrows():
        col = wide[z["zip"]]
        base = col.loc[base_idx].mean()
        vals = col.loc[qs]
        if np.isnan(base) or vals.isna().mean() > 0.2:
            continue
        vals = vals.interpolate(limit_direction="both")
        out_zips.append({
            "zip": z["zip"], "lat": round(float(z["lat"]), 4), "lon": round(float(z["lon"]), 4),
            "dist": round(float(z["dist"]), 2),
            "value_k": [round(float(np.exp(v)) / 1000, 1) for v in vals],
            "pct": [round(float((np.exp(v - base) - 1) * 100), 1) for v in vals],
        })
    return {"quarters": [f"{p.year}-{p.month:02d}" for p in qs], "zips": out_zips,
            "opened": f"{opened.year}-{opened.month:02d}"}


def chart_series(res: SCResult, step: int = 3, lo: int = -60, hi: int = 36) -> dict:
    rel = [m for m in res.treated_path.index if lo <= m <= hi and m % step == 0]
    idx = lambda s: [round(float(np.exp(s.loc[m]) * 100), 2) for m in rel]
    return {"months": rel, "actual": idx(res.treated_path), "synthetic": idx(res.synthetic_path)}


def export_all(zhvi: pd.DataFrame, zctas: pd.DataFrame, out_dir: Path, n_placebo: int = 40,
               only: str | None = None) -> pd.DataFrame:
    out_dir = Path(out_dir)
    (out_dir / "venues").mkdir(parents=True, exist_ok=True)
    wide = prepare_wide(zhvi)
    venues = pipeline.load_venues()
    if only:
        venues = venues[venues["venue_id"] == only]
    summary = []
    for _, v in venues.iterrows():
        res = meta = None
        try:
            res, meta = pipeline.venue_synthetic(v, zctas, wide, n_placebo=n_placebo)
        except ValueError as e:
            err = str(e)
        label, caveats = verdict(res, meta, int(v["opened_year"]))
        robust = None
        if label in ("signal", "suggestive"):
            alt, _ = pipeline.venue_synthetic(v, zctas, wide, n_placebo=n_placebo,
                                              density_match=ROBUST_DENSITY)
            robust = {"effect_pct": round(alt.effect_pct, 2), "p_value": round(alt.p_value, 4),
                      "n_donors": alt.n_donors}
            reason = robustness_downgrade(res, alt)
            if reason:
                caveats.append(reason)
                label = "suggestive" if label == "signal" else "inconclusive"
        entry = {
            "id": v["venue_id"], "name": v["name"], "team": v["team"], "league": v["league"],
            "city": v["city"], "state": v["state"], "lat": float(v["lat"]),
            "lon": float(v["lon"]), "opened_year": int(v["opened_year"]),
            "wikidata": v.get("wikidata_qid"), "verdict": label, "caveats": caveats,
        }
        if res is not None:
            entry["sc"] = {**{k: (None if x is None else round(float(x), 4))
                              for k, x in res.as_dict().items()},
                           "pre_months": meta["pre_months"]}
            entry["robustness"] = robust
            entry["chart"] = chart_series(res)
            entry["donors"] = [{"zip": z, "w": round(float(w), 3)}
                               for z, w in res.weights.head(5).items()]
        else:
            entry["error"] = err
        if res is not None or label == "no-data":
            (out_dir / "venues" / f"{v['venue_id']}.json").write_text(
                json.dumps(zip_series(v, zctas, wide), separators=(",", ":")))
        summary.append(entry)
        print(f"exported {v['venue_id']}: {label}", flush=True)
    (out_dir / "venues.json").write_text(json.dumps(summary, separators=(",", ":")))
    return pd.DataFrame(summary)
