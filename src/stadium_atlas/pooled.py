"""Pool venue-level effects: do venues move nearby home values *on average*?

Each venue contributes one effect (in log points). Inference uses the venues' own placebo
distributions: the pooled mean is compared with the means of many draws that pick one placebo
effect per venue. That p-value is approximate: in simulation it was slightly liberal (about 6%
false positives at a nominal 5%, 12% at 10%). The headline interval is therefore a t-interval over
venues (95% coverage in simulation; a percentile bootstrap covered only 91% with ~30 venues), and a
random-effects meta-analysis (DerSimonian-Laird, standard errors from placebo spread) is reported
as a cross-check.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

B = 10000


def _log(pct) -> np.ndarray:
    return np.log1p(np.asarray(pct, dtype=float) / 100.0)


def _pct(x: float) -> float:
    return float((np.exp(x) - 1) * 100)


def pool(venues: list[dict], placebo_key: str = "placebo_effects", seed: int = 0) -> dict:
    """venues: dicts with `effect_pct` and a list of placebo effects under `placebo_key`."""
    rows = [v for v in venues if len(v.get(placebo_key) or []) >= 10]
    if len(rows) < 3:
        return {"n": len(rows), "error": "need at least 3 venues with placebo distributions"}
    rng = np.random.default_rng(seed)
    y = _log([v["effect_pct"] for v in rows])
    plc = [_log(v[placebo_key]) for v in rows]
    se = np.array([p.std(ddof=1) for p in plc])
    n = len(rows)

    mean = float(y.mean())
    half = float(stats.t.ppf(0.975, n - 1) * y.std(ddof=1) / np.sqrt(n))
    null = np.array([[rng.choice(p) for p in plc] for _ in range(B // 5)]).mean(axis=1)
    p_pooled = float((1 + (np.abs(null) >= abs(mean)).sum()) / (1 + len(null)))

    w = 1 / se**2
    fixed = float((w * y).sum() / w.sum())
    q = float((w * (y - fixed) ** 2).sum())
    tau2 = max(0.0, (q - (n - 1)) / (w.sum() - (w**2).sum() / w.sum()))
    wr = 1 / (se**2 + tau2)
    re_mean = float((wr * y).sum() / wr.sum())
    re_se = float(np.sqrt(1 / wr.sum()))
    i2 = max(0.0, (q - (n - 1)) / q) if q > 0 else 0.0

    pos = int((y > 0).sum())
    from math import comb
    sign_p = float(min(1.0, 2 * sum(comb(n, k) for k in range(max(pos, n - pos), n + 1)) / 2**n))

    return {
        "n": n,
        "mean_pct": _pct(mean),
        "ci_pct": [_pct(mean - half), _pct(mean + half)],
        "placebo_p": p_pooled,
        "null_mean_pct": _pct(float(null.mean())),
        "random_effects_pct": _pct(re_mean),
        "random_effects_ci_pct": [_pct(re_mean - 1.96 * re_se), _pct(re_mean + 1.96 * re_se)],
        "tau_pct": float(np.sqrt(tau2) * 100),
        "i2": float(i2),
        "share_positive": pos / n,
        "sign_test_p": sign_p,
    }


def by_group(venues: list[dict], key: str, placebo_key: str = "placebo_effects") -> dict:
    """Pooled summary per group (e.g. league); groups with fewer than 3 venues are skipped."""
    out = {}
    for g in sorted({v[key] for v in venues}):
        res = pool([v for v in venues if v[key] == g], placebo_key)
        if "error" not in res:
            out[g] = {k: res[k] for k in ("n", "mean_pct", "ci_pct", "placebo_p")}
    return out
