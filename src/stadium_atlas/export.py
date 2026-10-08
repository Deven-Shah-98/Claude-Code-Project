"""Export per-venue results and ZIP time series as static JSON for the web app."""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from . import pipeline, pooled
from .geo import haversine_miles
from .synthetic import SCResult, prepare_wide

PANDEMIC_START_YEAR = 2019   # post-windows for venues opening from here include 2020-22
FEW_ZIPS = 5
MAP_RADIUS_MI = 15.0
ROBUST_DENSITY = 3.0       # donor land area cap (x treated median) for the robustness re-run
ROBUST_MIN_DONORS = 200    # below this the robustness pool is too thin to judge anything
GRID_MIN_AGREE = 0.75      # share of grid specifications that must share the primary's sign


def verdict(res: SCResult | None, meta: dict | None, opened_year: int,
            robust_reason: str | None = None) -> tuple[str, list[str]]:
    """Honest label + caveats. Order matters: data problems > pandemic > significance."""
    if res is None:
        return "no-data", ["Not enough pre-opening or ZIP-level data to estimate."]
    caveats = []
    if meta["low_confidence"]:
        caveats.append(f"Only {meta['pre_months']} months of pre-opening history (60 preferred).")
    if res.n_treated < FEW_ZIPS:
        caveats.append(f"Only {res.n_treated} ZIP codes in the treated area.")
    if meta.get("treated_radius", 3.0) > 3.0:
        caveats.append(f"Treated area widened to {meta['treated_radius']:g} miles "
                       "because too few nearby ZIPs had complete data.")
    if opened_year >= PANDEMIC_START_YEAR:
        caveats.append("Post-opening window overlaps the 2020-22 pandemic shift between urban "
                       "cores and suburbs.")
        if res.p_value_dense is not None:
            caveats.append(f"Among similarly sized ZIPs in the same years, an effect this large "
                           f"shows up about {res.p_value_dense * 100:.0f}% of the time "
                           f"(dense-area placebo p = {res.p_value_dense:.2f}).")
        return "confounded", caveats
    label = "inconclusive"
    if res.p_value is not None and res.p_value <= 0.10:
        label = "suggestive"
    if res.p_value is not None and res.p_value <= 0.05 and not meta["low_confidence"]:
        label = "signal"
    if label != "inconclusive":
        grid = meta.get("grid_summary") or {}
        if grid.get("n", 0) >= 6 and grid["share_same_sign"] < GRID_MIN_AGREE:
            caveats.append(f"Unstable across specifications: only "
                           f"{grid['share_same_sign'] * 100:.0f}% of {grid['n']} alternative "
                           "radius/window/donor choices keep the same direction.")
            label = "suggestive" if label == "signal" else "inconclusive"
        if robust_reason:
            caveats.append(robust_reason)
            label = "suggestive" if label == "signal" else "inconclusive"
    return label, caveats


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


_STATE: dict = {}


def _log_band(effect_pct: float, placebos: list[float]) -> tuple[float, float]:
    """Effect +/- 1.96 placebo standard deviations (log scale), back in percent."""
    sd = float(np.log1p(np.asarray(placebos) / 100).std(ddof=1))
    mid = float(np.log1p(effect_pct / 100))
    return (float((np.exp(mid - 1.96 * sd) - 1) * 100), float((np.exp(mid + 1.96 * sd) - 1) * 100))


def _process_venue(args: tuple) -> dict:
    """Worker: one venue's estimate, robustness, JSON entry, ZIP series and placebo draws."""
    v, n_placebo = args
    zctas, wide = _STATE["zctas"], _STATE["wide"]
    res = meta = None
    err = ""
    try:
        res, meta = pipeline.venue_synthetic(v, zctas, wide, n_placebo=n_placebo, grid=True)
    except ValueError as e:
        err = str(e)
    robust = reason = None
    if res is not None and res.p_value is not None and res.p_value <= 0.10 \
            and int(v["opened_year"]) < PANDEMIC_START_YEAR:
        alt, _ = pipeline.venue_synthetic(v, zctas, wide, n_placebo=n_placebo,
                                          density_match=ROBUST_DENSITY)
        robust = {"effect_pct": round(alt.effect_pct, 2), "p_value": round(alt.p_value, 4),
                  "n_donors": alt.n_donors}
        reason = robustness_downgrade(res, alt)
    label, caveats = verdict(res, meta, int(v["opened_year"]), reason)
    entry = {
        "id": v["venue_id"], "name": v["name"], "team": v["team"], "league": v["league"],
        "city": v["city"], "state": v["state"], "lat": float(v["lat"]), "lon": float(v["lon"]),
        "opened_year": int(v["opened_year"]), "opened_month": pipeline.opening_month(v),
        "wikidata": v.get("wikidata_qid"), "verdict": label, "caveats": caveats,
    }
    placebos = {}
    if res is not None:
        entry["sc"] = {**{k: (None if x is None else round(float(x), 4))
                          for k, x in res.as_dict().items()},
                       "pre_months": meta["pre_months"], "treated_radius": meta["treated_radius"]}
        entry["robustness"] = robust
        entry["grid"] = {"rows": meta["grid"], "summary": meta["grid_summary"]}
        entry["chart"] = chart_series(res)
        entry["donors"] = [{"zip": z, "w": round(float(w), 3)}
                           for z, w in res.weights.head(5).items()]
        entry["band_pct"] = [round(x, 2) for x in _log_band(res.effect_pct, res.placebo_effects)]
        placebos = {"placebo_effects": res.placebo_effects,
                    "placebo_effects_dense": res.placebo_effects_dense}
    else:
        entry["error"] = err
    series = zip_series(v, zctas, wide) if (res is not None or label == "no-data") else None
    return {"entry": entry, "series": series, "placebos": placebos}


def era(year: int) -> str:
    """Opening era. 2006-2009 venues have post-windows inside the 2008-11 housing bust."""
    if year <= 2007:
        return "2003-07"
    return "2008-11" if year <= 2011 else "2012-18"


def pooled_summary(entries: list[dict], placebos: dict[str, dict]) -> dict:
    """Pool scorable venues; pandemic-window venues are reported separately, never mixed in."""
    def rows(pred):
        return [{**e["sc"], "id": e["id"], "league": e["league"], "era": era(e["opened_year"]),
                 "effect_pct": e["sc"]["effect_pct"], **placebos[e["id"]]}
                for e in entries if "sc" in e and pred(e)]

    main = rows(lambda e: e["verdict"] != "confounded")
    pandemic = rows(lambda e: e["verdict"] == "confounded")
    return {
        "n_venues_total": len(entries),
        "n_scored": len(main) + len(pandemic),
        "all": pooled.pool(main),
        "dense_null": pooled.pool(main, "placebo_effects_dense"),
        "by_league": pooled.by_group(main, "league"),
        "by_era": pooled.by_group(main, "era"),
        "pandemic_window": pooled.pool(pandemic) if len(pandemic) >= 3 else {"n": len(pandemic)},
        "forest": [{"id": e["id"], "name": e["name"], "league": e["league"], "year": e["opened_year"],
                    "effect_pct": e["sc"]["effect_pct"], "band_pct": e["band_pct"],
                    "verdict": e["verdict"]} for e in entries if "sc" in e],
    }


def export_all(zhvi: pd.DataFrame, zctas: pd.DataFrame, out_dir: Path, n_placebo: int = 40,
               only: str | None = None, workers: int = 4) -> pd.DataFrame:
    out_dir = Path(out_dir)
    (out_dir / "venues").mkdir(parents=True, exist_ok=True)
    venues = pipeline.load_venues()
    if only:
        venues = venues[venues["venue_id"] == only]
    _STATE.update(zctas=zctas, wide=prepare_wide(zhvi))   # inherited by forked workers
    jobs = [(v, n_placebo) for _, v in venues.iterrows()]
    # One math thread per worker: several workers each spawning BLAS threads oversubscribe the
    # cores and run many times slower than the same work single-threaded.
    for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[var] = "1"
    t0, results = time.time(), [None] * len(jobs)
    if workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(workers, mp_context=mp.get_context("fork")) as ex:
            futures = {ex.submit(_process_venue, j): i for i, j in enumerate(jobs)}
            for n, fut in enumerate(as_completed(futures), start=1):
                results[futures[fut]] = fut.result()
                e = results[futures[fut]]["entry"]
                print(f"[{n}/{len(jobs)}] {e['id']}: {e['verdict']} ({time.time() - t0:.0f}s)", flush=True)
    else:
        for i, j in enumerate(jobs):
            results[i] = _process_venue(j)
            print(f"[{i + 1}/{len(jobs)}] {results[i]['entry']['id']} ({time.time() - t0:.0f}s)", flush=True)
    entries, placebos = [], {}
    for r in results:
        e = r["entry"]
        entries.append(e)
        placebos[e["id"]] = r["placebos"]
        if r["series"] is not None:
            (out_dir / "venues" / f"{e['id']}.json").write_text(
                json.dumps(r["series"], separators=(",", ":")))
    (out_dir / "venues.json").write_text(json.dumps(entries, separators=(",", ":")))
    (out_dir / "pooled.json").write_text(json.dumps(pooled_summary(entries, placebos),
                                                    separators=(",", ":")))
    proc = Path("data/processed")
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "placebos.json").write_text(json.dumps(placebos))
    return pd.DataFrame(entries)


def repool(data_dir: str = "web/public/data") -> dict:
    """Recompute pooled.json from the saved venues.json and placebo draws (no re-estimation)."""
    data = Path(data_dir)
    entries = json.loads((data / "venues.json").read_text())
    placebos = json.loads(Path("data/processed/placebos.json").read_text())
    out = pooled_summary(entries, placebos)
    (data / "pooled.json").write_text(json.dumps(out, separators=(",", ":")))
    return out
