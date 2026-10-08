"""Simplified ZIP-code and state boundaries as compact JSON for the web map.

Source: Census cartographic boundary files (public domain), 2020 ZCTAs (1:500k) and states (1:20m).
Shapes are simplified (about 40 m) and rounded to 4 decimals so each venue's file stays small.
A polygon is a list of rings; a ZIP or state is a list of polygons; a ring is [[lon, lat], ...].
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import shapefile
from shapely.geometry import shape

ZCTA_SHP = "data/raw/cb_2020_us_zcta520_500k.zip"
STATE_SHP = "data/raw/cb_2020_us_state_20m.zip"


def _reader(zip_path: str) -> shapefile.Reader:
    """Open the shapefile inside a Census zip without extracting it."""
    with zipfile.ZipFile(zip_path) as z:
        part = {ext: io.BytesIO(z.read(n)) for n in z.namelist()
                for ext in ("shp", "shx", "dbf") if n.endswith(f".{ext}")}
    return shapefile.Reader(shp=part["shp"], shx=part["shx"], dbf=part["dbf"])


def _rings(geom, ndigits: int) -> list[list[list[list[float]]]]:
    polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    out = []
    for p in polys:
        if p.is_empty or p.geom_type != "Polygon":
            continue
        rings = [list(p.exterior.coords)] + [list(r.coords) for r in p.interiors]
        out.append([[[round(x, ndigits), round(y, ndigits)] for x, y in r] for r in rings])
    return out


def zcta_shapes(zips: set[str], path: str = ZCTA_SHP, tol: float = 0.0004) -> dict:
    """Simplified polygons for the requested ZIPs (one pass over the national file)."""
    out: dict = {}
    reader = _reader(path)
    fields = [f[0] for f in reader.fields[1:]]
    key = next(f for f in fields if f.startswith("GEOID"))
    for sr in reader.iterShapeRecords():
        z = sr.record[fields.index(key)]
        if z in zips:
            geom = shape(sr.shape.__geo_interface__).simplify(tol, preserve_topology=True)
            polys = _rings(geom, 4)
            if polys:
                out[z] = polys
    return out


def state_outlines(path: str = STATE_SHP, tol: float = 0.02) -> list[dict]:
    """Lower-48 + DC outlines (drops AK, HI, territories) for the overview backdrop."""
    reader = _reader(path)
    fields = [f[0] for f in reader.fields[1:]]
    out = []
    for sr in reader.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        if rec["STUSPS"] in {"AK", "HI", "PR", "VI", "GU", "AS", "MP"}:
            continue
        geom = shape(sr.shape.__geo_interface__).simplify(tol, preserve_topology=True)
        out.append({"state": rec["STUSPS"], "polys": _rings(geom, 2)})
    return out


def export_geo(data_dir: str = "web/public/data") -> dict:
    """Write venues/<id>.shapes.json for every exported venue, plus states.json."""
    data = Path(data_dir)
    series = {p.stem: json.loads(p.read_text()) for p in (data / "venues").glob("*.json")
              if not p.name.endswith(".shapes.json")}
    wanted = {z["zip"] for s in series.values() for z in s["zips"]}
    shapes = zcta_shapes(wanted)
    written = 0
    for vid, s in series.items():
        sub = {z["zip"]: shapes[z["zip"]] for z in s["zips"] if z["zip"] in shapes}
        (data / "venues" / f"{vid}.shapes.json").write_text(json.dumps(sub, separators=(",", ":")))
        written += 1
    (data / "states.json").write_text(json.dumps(state_outlines(), separators=(",", ":")))
    return {"venues": written, "zips_requested": len(wanted), "zips_found": len(shapes)}
