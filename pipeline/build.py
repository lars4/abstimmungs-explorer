"""Command line entry point.

  python -m pipeline.build demo                 synthetic data, no network (for development)
  python -m pipeline.build live                 canton history + municipalities + latest votes
  python -m pipeline.build live --no-municipalities --since 1990
  python -m pipeline.build inspect              print BFS table variables (debugging)
"""
from __future__ import annotations

import argparse
import json
import sys

from . import bfs_px, demo, voteinfo
from .common import DATA_DIR
from .store import Store


def parse_map(items: list[str]) -> dict:
    out = {}
    for it in items or []:
        role, _, code = it.partition("=")
        out[role] = code
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.build", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="write synthetic demo data")
    sub.add_parser("inspect", help="print variables of the BFS PxWeb tables")
    live = sub.add_parser("live", help="fetch real data")
    live.add_argument("--since", type=int, default=None, help="only votes from this year on (canton table)")
    live.add_argument("--muni-since", type=int, default=1990, help="municipality results from this year on")
    live.add_argument("--no-municipalities", action="store_true")
    live.add_argument("--no-voteinfo", action="store_true", help="skip latest-vote gap filling")
    live.add_argument("--max-cells", type=int, default=20000, help="PxWeb cells per request")
    live.add_argument("--map", action="append", default=[], metavar="ROLE=CODE",
                      help="override PxWeb variable role (vote, canton, muni, measure)")
    for p in (live, sub.choices["demo"]):
        p.add_argument("--out", default=str(DATA_DIR))
    args = ap.parse_args(argv)

    if args.cmd == "inspect":
        for t in (bfs_px.CANTON_TABLE, bfs_px.MUNI_TABLE):
            meta = bfs_px.fetch_table_meta(t)
            print(f"== {t}: {meta.get('title')}")
            for v in meta["variables"]:
                print(f"  {v['code']!r:28} {v['text']!r:34} {len(v['values'])} values; e.g. {v['valueTexts'][:3]}")
        return 0

    store = Store()
    if args.cmd == "demo":
        demo.generate(store)
    else:
        override = parse_map(args.map)
        print("BFS canton table …", file=sys.stderr)
        bfs_px.load_cantons(store, args.max_cells, args.since, override)
        if not args.no_municipalities:
            print("BFS municipality table …", file=sys.stderr)
            bfs_px.load_municipalities(store, args.max_cells, args.muni_since, override)
        if not args.no_voteinfo:
            print("opendata.swiss latest votes …", file=sys.stderr)
            n = voteinfo.load_missing(store, municipalities=not args.no_municipalities)
            print(f"  added {n} proposals", file=sys.stderr)
        if not store.votes:
            print("No votes loaded - aborting without overwriting data.", file=sys.stderr)
            return 1
    from pathlib import Path
    store.write(Path(args.out))
    print(json.dumps({"votes": len(store.votes), "demo": store.demo}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
