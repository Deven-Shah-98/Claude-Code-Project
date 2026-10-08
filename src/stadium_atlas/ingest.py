"""Download and parse public datasets (Zillow ZHVI, Census ZCTA gazetteer).

Network hosts used: files.zillowstatic.com, www2.census.gov.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

ZHVI_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zhvi/"
    "Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
)
ZCTA_GAZ_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2020_Gazetteer/"
    "2020_Gaz_zcta_national.zip"
)

RAW_DIR = Path("data/raw")


def download(url: str, dest: Path, *, force: bool = False, timeout: int = 120) -> Path:
    """Download `url` to `dest` unless cached. Streams to a temp file, then renames."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            f.writelines(r.iter_content(1 << 20))
    tmp.replace(dest)
    return dest


def parse_zhvi(source) -> pd.DataFrame:
    """Wide Zillow ZHVI CSV -> long frame: zip, metro, state, date, value."""
    wide = pd.read_csv(source, dtype={"RegionName": str})
    id_cols = [c for c in ("RegionName", "Metro", "State") if c in wide.columns]
    date_cols = [c for c in wide.columns if c[:2] in ("19", "20") and c[4:5] == "-"]
    long = wide.melt(id_vars=id_cols, value_vars=date_cols, var_name="date", value_name="value")
    long = long.rename(columns={"RegionName": "zip", "Metro": "metro", "State": "state"})
    long["zip"] = long["zip"].str.zfill(5)
    long["date"] = pd.to_datetime(long["date"])
    return long.dropna(subset=["value"]).sort_values(["zip", "date"]).reset_index(drop=True)


def parse_zcta_gazetteer(source) -> pd.DataFrame:
    """Census gazetteer (tab-delimited, optionally zipped) -> zip, lat, lon, land_sqmi."""
    if isinstance(source, (str, Path)) and str(source).endswith(".zip"):
        with zipfile.ZipFile(source) as z:
            name = next(n for n in z.namelist() if n.endswith(".txt"))
            source = io.BytesIO(z.read(name))
    df = pd.read_csv(source, sep="\t", dtype={"GEOID": str})
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={"GEOID": "zip", "INTPTLAT": "lat", "INTPTLONG": "lon",
                            "ALAND_SQMI": "land_sqmi"})
    return df[["zip", "lat", "lon", "land_sqmi"]]


def fetch_all(force: bool = False) -> tuple[Path, Path]:
    zhvi = download(ZHVI_URL, RAW_DIR / "zhvi_zip.csv", force=force)
    gaz = download(ZCTA_GAZ_URL, RAW_DIR / "zcta_gazetteer.zip", force=force)
    return zhvi, gaz
