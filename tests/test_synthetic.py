import numpy as np
import pandas as pd
import pytest

from stadium_atlas.synthetic import fit_weights, placebo_test, prepare_wide, synthetic_control

EVENT = pd.Timestamp("2010-04-01")


def factor_world(effect=0.10, n_markets=14, zips_per_market=6, seed=3):
    """Markets of nearby ZIPs sharing exposure to 3 national trends; one market is treated.

    Mirrors reality: neighbouring ZIPs move together, the treated market is just another market
    (same loading distribution), and a post-event step is added to treated ZIPs only.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2005-01-01", "2014-12-01", freq="MS")
    T = len(dates)
    t = np.arange(T)
    factors = np.stack([0.004 * t, 0.15 * np.sin(t / 15), np.cumsum(rng.normal(0, 0.01, T))])
    post = (dates >= EVENT).astype(float)
    rows, geo, treated_zips = [], [], []
    for m in range(n_markets + 1):
        treated = m == n_markets
        load = rng.dirichlet([1, 1, 1]) * [1.6, 1, 1]
        lat0, lon0 = (40.0, -100.0) if treated else (rng.uniform(30, 48), rng.uniform(-125, -75))
        for j in range(zips_per_market):
            z = f"m{m}z{j}"
            series = 12 + load @ factors + rng.normal(0, 0.004, T)
            if treated:
                series = series + effect * post
                treated_zips.append(z)
            rows += [(z, d, float(np.exp(v))) for d, v in zip(dates, series)]
            geo.append((z, lat0 + rng.normal(0, 0.02), lon0 + rng.normal(0, 0.02)))
    return (pd.DataFrame(rows, columns=["zip", "date", "value"]),
            pd.DataFrame(geo, columns=["zip", "lat", "lon"]), treated_zips)


def test_fit_weights_simplex_and_recovery():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(50, 6))
    w_true = np.array([0.5, 0.3, 0.2, 0, 0, 0])
    w = fit_weights(X, X @ w_true)
    assert w.sum() == pytest.approx(1.0)
    assert (w >= 0).all()
    assert w == pytest.approx(w_true, abs=0.02)


def test_synthetic_control_recovers_effect_with_good_prefit():
    zhvi, _, treated = factor_world(effect=0.10)
    r = synthetic_control(prepare_wide(zhvi), treated, EVENT, pre_months=60, post_months=36)
    assert r.effect_pct == pytest.approx(10.5, abs=2.0)
    assert r.pre_rmspe < 0.03
    assert r.weights.sum() == pytest.approx(1.0, abs=1e-6)
    assert (r.gap.loc[-12:-1].abs() < 0.05).all()


def test_synthetic_control_null_is_near_zero():
    zhvi, _, treated = factor_world(effect=0.0, seed=5)
    r = synthetic_control(prepare_wide(zhvi), treated, EVENT)
    assert abs(r.effect_pct) < 2.5


def _placebo_p(effect, seed):
    zhvi, zctas, treated = factor_world(effect=effect, seed=seed)
    wide = prepare_wide(zhvi)
    r = synthetic_control(wide, treated, EVENT)
    placebo_test(wide, zctas, r, EVENT, exclude_zips=treated, n_placebo=12, seed=seed)
    assert r.n_placebos >= 8
    return r.p_value


def test_placebo_pvalue_flags_real_effects_but_rarely_nulls():
    seeds = range(20, 24)
    real = [_placebo_p(0.15, s) for s in seeds]
    null = [_placebo_p(0.0, s) for s in seeds]
    assert all(p <= 0.1 for p in real), real
    # a null should look "significant" only about as often as the nominal rate, not routinely
    assert sum(p <= 0.1 for p in null) <= 1, null


def test_too_few_treated_raises():
    zhvi, _, treated = factor_world()
    with pytest.raises(ValueError):
        synthetic_control(prepare_wide(zhvi), treated[:1], EVENT)
