import pandas as pd
import pytest

from stadium_atlas.geo import assign_rings, haversine_miles


def test_haversine_sf_to_la():
    d = haversine_miles(37.7749, -122.4194, 34.0522, -118.2437)
    assert d == pytest.approx(347, abs=3)


def test_assign_rings_buckets_and_drops_far():
    z = pd.DataFrame({
        "zip": ["a", "b", "c", "d"],
        "lat": [37.7786, 37.80, 37.85, 38.9],
        "lon": [-122.3893, -122.39, -122.39, -122.39],
    })
    out = assign_rings(z, 37.7786, -122.3893).set_index("zip")
    assert out.loc["a", "ring"] == "0-1.5mi"
    assert out.loc["c", "ring"] in ("3-5mi", "control")
    assert "d" not in out.index  # >15 miles away
