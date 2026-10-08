import io

from stadium_atlas.ingest import parse_zcta_gazetteer, parse_zhvi

ZHVI = """RegionID,SizeRank,RegionName,RegionType,StateName,State,City,Metro,CountyName,2020-01-31,2020-02-29
1,1,2108,zip,MA,MA,Boston,Boston-Cambridge-Newton,Suffolk,500000,510000
2,2,94107,zip,CA,CA,San Francisco,San Francisco-Oakland,SF,,900000
"""

GAZ = "GEOID\tALAND_SQMI\tINTPTLAT\tINTPTLONG  \n02108\t0.1\t42.357\t-71.064\n"


def test_parse_zhvi_long_format_pads_zip_and_drops_na():
    df = parse_zhvi(io.StringIO(ZHVI))
    assert set(df.columns) == {"zip", "metro", "state", "date", "value"}
    assert "02108" in set(df["zip"])
    assert len(df) == 3  # one NaN dropped
    assert df["date"].dtype.kind == "M"


def test_parse_gazetteer_strips_column_whitespace():
    df = parse_zcta_gazetteer(io.StringIO(GAZ))
    assert list(df.columns) == ["zip", "lat", "lon"]
    assert df.loc[0, "zip"] == "02108"
