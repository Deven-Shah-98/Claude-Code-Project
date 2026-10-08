"""Distance and ring assignment around a venue."""
from __future__ import annotations

import numpy as np
import pandas as pd

EARTH_RADIUS_MILES = 3958.8

# (label, inner_mi, outer_mi). "control" is a donut well outside venue influence.
DEFAULT_RINGS: tuple[tuple[str, float, float], ...] = (
    ("0-1.5mi", 0.0, 1.5),
    ("1.5-3mi", 1.5, 3.0),
    ("3-5mi", 3.0, 5.0),
    ("control", 5.0, 15.0),
)


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles. Accepts scalars or numpy arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def assign_rings(zctas: pd.DataFrame, lat: float, lon: float, rings=DEFAULT_RINGS) -> pd.DataFrame:
    """Return zctas within the outermost ring, with `distance_mi` and `ring` columns.

    `zctas` needs `zip`, `lat`, `lon`. Rings are half-open: inner <= d < outer.
    """
    out = zctas.copy()
    out["distance_mi"] = haversine_miles(lat, lon, out["lat"].to_numpy(), out["lon"].to_numpy())
    out["ring"] = pd.NA
    for label, inner, outer in rings:
        out.loc[(out["distance_mi"] >= inner) & (out["distance_mi"] < outer), "ring"] = label
    return out.dropna(subset=["ring"]).reset_index(drop=True)
