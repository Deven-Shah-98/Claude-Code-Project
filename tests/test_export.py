import pandas as pd

from stadium_atlas.export import robustness_downgrade, verdict
from stadium_atlas.synthetic import SCResult


def _res(effect, p, donors=1000, n_treated=10):
    return SCResult(effect_pct=effect, pre_rmspe=0.003, post_rmspe=0.05, gap=pd.Series(dtype=float),
                    weights=pd.Series(dtype=float), n_treated=n_treated, n_donors=donors, p_value=p)


META = {"low_confidence": False, "pre_months": 60}


def test_verdict_ordering():
    assert verdict(None, None, 2010)[0] == "no-data"
    assert verdict(_res(30, 0.03), META, 2012)[0] == "signal"
    assert verdict(_res(30, 0.03), META, 2020)[0] == "confounded"
    assert verdict(_res(5, 0.07), META, 2012)[0] == "suggestive"
    assert verdict(_res(5, 0.4), META, 2012)[0] == "inconclusive"
    assert verdict(_res(30, 0.03), {"low_confidence": True, "pre_months": 40}, 2012)[0] != "signal"


def test_robustness_downgrade_rules():
    primary = _res(31.7, 0.03)
    assert robustness_downgrade(primary, _res(18.1, 0.13))            # lost significance
    assert robustness_downgrade(primary, _res(-10, 0.03))             # sign flipped
    assert robustness_downgrade(primary, _res(25, 0.05)) is None      # agrees
    assert robustness_downgrade(primary, _res(5, 0.9, donors=28)) is None  # pool too thin to judge


def test_verdict_downgrades_on_unstable_grid_and_explains_pandemic_with_dense_placebo():
    unstable = {**META, "grid_summary": {"n": 12, "share_same_sign": 0.5}}
    label, caveats = verdict(_res(30, 0.03), unstable, 2012)
    assert label == "suggestive" and any("Unstable across specifications" in c for c in caveats)
    stable = {**META, "grid_summary": {"n": 12, "share_same_sign": 1.0}}
    assert verdict(_res(30, 0.03), stable, 2012)[0] == "signal"
    assert verdict(_res(5, 0.4), unstable, 2012)[0] == "inconclusive"   # nothing to downgrade

    res = _res(-18, 0.03)
    res.p_value_dense = 0.14
    label, caveats = verdict(res, META, 2019)
    assert label == "confounded" and any("dense-area placebo p = 0.14" in c for c in caveats)

    widened = {**META, "treated_radius": 7.0}
    assert any("widened to 7 miles" in c for c in verdict(_res(5, 0.4), widened, 2012)[1])


def test_pooled_summary_keeps_pandemic_venues_out_of_the_main_pool():
    import numpy as np

    from stadium_atlas.export import pooled_summary

    rng = np.random.default_rng(0)

    def entry(i, effect, verdict_):
        return {"id": f"v{i}", "name": f"V{i}", "league": "MLB" if i % 2 else "NFL",
                "opened_year": 2010 if verdict_ != "confounded" else 2020, "verdict": verdict_,
                "sc": {"effect_pct": effect}, "band_pct": [effect - 5, effect + 5]}

    entries = [entry(i, float(rng.normal(3, 4)), "inconclusive") for i in range(12)]
    entries += [entry(100 + i, -15.0, "confounded") for i in range(3)]
    placebos = {e["id"]: {"placebo_effects": rng.normal(0, 4, 30).tolist(),
                          "placebo_effects_dense": rng.normal(0, 6, 30).tolist()} for e in entries}
    out = pooled_summary(entries, placebos)
    assert out["all"]["n"] == 12 and out["pandemic_window"]["n"] == 3
    assert out["pandemic_window"]["mean_pct"] < -10          # not diluted into the main estimate
    assert out["dense_null"]["n"] == 12 and len(out["forest"]) == 15
