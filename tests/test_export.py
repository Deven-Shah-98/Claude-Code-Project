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
