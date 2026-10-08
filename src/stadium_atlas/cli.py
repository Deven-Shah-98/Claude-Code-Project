"""`atlas` command line: fetch data, score venues."""
from __future__ import annotations

import argparse
import json

import pandas as pd

from . import ingest, pipeline


def _load():
    zhvi_path, gaz_path = ingest.fetch_all()
    return ingest.parse_zhvi(zhvi_path), ingest.parse_zcta_gazetteer(gaz_path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="atlas")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="download raw public datasets into data/raw")
    sc = sub.add_parser("score", help="stadium effect estimate for one or all venues")
    sc.add_argument("--venue", help="venue_id from data/seed/venues.csv (default: all)")
    args = p.parse_args(argv)

    if args.cmd == "fetch":
        for path in ingest.fetch_all():
            print(f"ok {path}")
        return 0

    zhvi, zctas = _load()
    venues = pipeline.load_venues()
    if args.venue:
        venues = venues[venues["venue_id"] == args.venue]
    rows = []
    for _, v in venues.iterrows():
        try:
            est, _ = pipeline.venue_effect(v, zctas, zhvi)
            rows.append({"venue_id": v["venue_id"], **est.as_dict()})
        except ValueError as e:
            rows.append({"venue_id": v["venue_id"], "error": str(e)})
    print(json.dumps(rows, indent=2) if args.venue else pd.DataFrame(rows).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
