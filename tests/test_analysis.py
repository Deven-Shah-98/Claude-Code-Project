import numpy as np
import pandas as pd
import pytest

from stadium_atlas.analysis import did_effect, event_study

EVENT = pd.Timestamp("2010-04-01")


def synthetic_panel(effect=0.10, n_treated=12, n_control=30, seed=1, treated_drift=0.0):
    """Monthly ZIP values; treated ZIPs get a +`effect` log-point step after EVENT."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2004-01-01", "2016-12-01", freq="MS")
    rows = []
    for i in range(n_treated + n_control):
        treated = i < n_treated
        base = rng.normal(12.5, 0.3)
        trend = 0.004 + (treated_drift if treated else 0.0)
        for k, d in enumerate(dates):
            step = effect if treated and d >= EVENT else 0.0
            log_v = base + trend * k + step + rng.normal(0, 0.005)
            rows.append((f"z{i}", d, float(np.exp(log_v)), "0-1.5mi" if treated else "control"))
    return pd.DataFrame(rows, columns=["zip", "date", "value", "ring"])


def test_did_recovers_injected_effect():
    est = did_effect(synthetic_panel(effect=0.10), EVENT)
    assert est.effect_pct == pytest.approx(10.5, abs=1.5)  # exp(.1)-1
    assert est.ci_low_pct < est.effect_pct < est.ci_high_pct
    assert est.significant
    assert abs(est.pretrend_pct_per_year) < 0.5


def test_did_null_effect_not_significant():
    est = did_effect(synthetic_panel(effect=0.0, seed=7), EVENT)
    assert abs(est.effect_pct) < 1.5
    assert not est.significant


def test_pretrend_diagnostic_flags_preexisting_drift():
    est = did_effect(synthetic_panel(effect=0.0, treated_drift=0.003), EVENT)
    assert est.pretrend_pct_per_year > 2.0  # ~0.003*12 = 3.7%/yr


def test_did_requires_enough_zips():
    with pytest.raises(ValueError):
        did_effect(synthetic_panel(n_treated=1), EVENT)


def test_event_study_gap_jumps_at_event():
    es = event_study(synthetic_panel(effect=0.10), EVENT)
    t = es[es["ring"] == "0-1.5mi"].set_index("rel_month")["gap_vs_control"]
    assert abs(t.loc[-6]) < 0.02
    assert t.loc[12] == pytest.approx(0.10, abs=0.02)
    assert (es[es["ring"] == "control"]["gap_vs_control"].abs() < 1e-9).all()


def test_venue_effect_shrinks_pre_window_and_rejects_short_history():
    from stadium_atlas.pipeline import venue_effect

    panel = synthetic_panel(effect=0.05)
    zhvi = panel[["zip", "date", "value"]]
    zctas = pd.DataFrame({"zip": panel["zip"].unique()})
    zctas["lat"] = 40.0
    zctas["lon"] = np.where(zctas["zip"].str[1:].astype(int) < 12, -100.0, -100.1)
    base = {"lat": 40.0, "lon": -100.0}
    # data starts 2004-01, opening 2006-04 -> only 27 months of pre history; should still run
    ok = pd.Series({**base, "opened_year": 2006})
    try:
        venue_effect(ok, zctas, zhvi)
    except ValueError as e:  # ring layout in this toy setup may not give both groups
        assert "insufficient pre-period" not in str(e)
    short = pd.Series({**base, "opened_year": 2004})
    with pytest.raises(ValueError, match="insufficient pre-period"):
        venue_effect(short, zctas, zhvi)
