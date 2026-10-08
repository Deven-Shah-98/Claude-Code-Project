import numpy as np
import pytest

from stadium_atlas.pooled import by_group, pool
from stadium_atlas.robustness import summarize
from stadium_atlas.synthetic import p_value


def fake_venues(true_effect, n=30, seed=0, sd=0.05):
    """Venue effects = true effect + noise; each venue's placebos have the same noise scale."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        eff = (np.exp(rng.normal(true_effect, sd)) - 1) * 100
        plc = ((np.exp(rng.normal(0, sd, 40)) - 1) * 100).tolist()
        out.append({"id": f"v{i}", "league": "MLB" if i % 2 else "NFL", "effect_pct": eff,
                    "placebo_effects": plc})
    return out


def test_pool_detects_true_average_effect():
    r = pool(fake_venues(0.08))
    assert 5 < r["mean_pct"] < 12
    assert r["ci_pct"][0] > 0 and r["placebo_p"] < 0.05
    assert r["share_positive"] > 0.8


def test_pool_null_is_rarely_flagged(monkeypatch):
    monkeypatch.setattr("stadium_atlas.pooled.B", 1000)
    runs = [pool(fake_venues(0.0, seed=s)) for s in range(40, 60)]
    assert all(abs(r["mean_pct"]) < 4 for r in runs)
    # nominal 5% (about 6% measured); allow a generous margin for 20 draws
    assert sum(r["placebo_p"] <= 0.05 for r in runs) <= 4
    assert sum(r["ci_pct"][0] > 0 or r["ci_pct"][1] < 0 for r in runs) <= 4


def test_pool_needs_enough_venues_and_by_group_splits():
    assert "error" in pool(fake_venues(0.0, n=2))
    g = by_group(fake_venues(0.08), "league")
    assert set(g) == {"MLB", "NFL"} and all(v["n"] == 15 for v in g.values())


def test_p_value_and_robustness_summary():
    assert p_value(10.0, [1, -2, 3, -4]) == pytest.approx(1 / 5)
    assert p_value(0.5, [1, -2, 3, -4]) == pytest.approx(1.0)
    s = summarize([{"effect_pct": 10}, {"effect_pct": 20}, {"effect_pct": -5}], 12.0)
    assert s["n"] == 3 and s["share_same_sign"] == pytest.approx(2 / 3, abs=1e-3) and s["max"] == 20
    assert summarize([], 1.0) == {"n": 0}
