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
    sy = sub.add_parser("synth", help="synthetic-control estimate + placebo p-value")
    sy.add_argument("--venue", help="venue_id (default: all)")
    sy.add_argument("--placebos", type=int, default=40)
    sv = sub.add_parser("serve", help="serve the web app with the /api/ask question endpoint")
    sv.add_argument("--port", type=int, default=8000)
    ex = sub.add_parser("export", help="write static JSON for the web app")
    ex.add_argument("--out", default="web/public/data")
    ex.add_argument("--placebos", type=int, default=40)
    ex.add_argument("--venue", help="export a single venue_id (default: all)")
    args = p.parse_args(argv)

    if args.cmd == "serve":
        from .server import serve

        serve(port=args.port)
        return 0
    if args.cmd == "fetch":
        for path in ingest.fetch_all():
            print(f"ok {path}")
        return 0

    zhvi, zctas = _load()
    venues = pipeline.load_venues()
    if args.cmd == "export":
        from .export import export_all

        export_all(zhvi, zctas, args.out, n_placebo=args.placebos, only=args.venue)
        return 0
    if args.cmd == "synth":
        return _synth(args, zhvi, zctas, venues)
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


def _synth(args, zhvi, zctas, venues) -> int:
    from pathlib import Path

    from .synthetic import prepare_wide

    wide = prepare_wide(zhvi)
    if args.venue:
        venues = venues[venues["venue_id"] == args.venue]
    out_dir = Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, gaps = [], {}
    for _, v in venues.iterrows():
        try:
            res, meta = pipeline.venue_synthetic(v, zctas, wide, n_placebo=args.placebos)
        except ValueError as e:
            rows.append({"venue_id": v["venue_id"], "error": str(e)})
            continue
        rows.append({"venue_id": v["venue_id"], **res.as_dict(), **meta})
        gaps[v["venue_id"]] = {int(k): float(x) for k, x in res.gap.items()}
    table = pd.DataFrame(rows)
    table.to_csv(out_dir / "synthetic_results.csv", index=False)
    (out_dir / "synthetic_gaps.json").write_text(json.dumps(gaps))
    print(table.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
