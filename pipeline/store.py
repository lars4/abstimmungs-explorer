"""In-memory result store that serialises to the compact JSON layout used by the web app.

Layout written to web/data/:
  votes.json                 list of votes (one entry per proposal) + meta
  cantons.json               {voteId: {canton: [yesPct, turnoutPct]}}
  municipalities/<CT>.json   {"names": {bfs: name}, "results": {voteId: {bfs: [yes, turnout]}}}
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
from collections import defaultdict

from .common import CANTON_BY_CODE, round1


class Store:
    def __init__(self) -> None:
        self.votes: dict[str, dict] = {}
        self.cantons: dict[str, dict[str, list]] = {}
        self.munis: dict[str, dict] = defaultdict(lambda: {"names": {}, "results": defaultdict(dict)})
        self.sources: set[str] = set()
        self.demo = False

    # -- votes ---------------------------------------------------------
    def dates(self) -> set[str]:
        return {v["date"] for v in self.votes.values()}

    def next_id(self, date: str) -> str:
        n = 1 + sum(1 for v in self.votes.values() if v["date"] == date)
        return f"{date.replace('-', '')}-{n}"

    def add_vote(self, vote_id: str, date: str, title: dict, kind: str | None = None,
                 yes=None, turnout=None, accepted=None, source: str = "") -> None:
        yes, turnout = round1(yes), round1(turnout)
        if accepted is None and yes is not None:
            accepted = yes > 50
        self.votes[vote_id] = {
            "id": vote_id, "date": date, "title": title, "kind": kind,
            "yes": yes, "turnout": turnout, "accepted": accepted,
        }
        if source:
            self.sources.add(source)

    def add_canton(self, vote_id: str, code: str, yes, turnout) -> None:
        if code not in CANTON_BY_CODE:
            return
        y, t = round1(yes), round1(turnout)
        if y is None:
            return
        self.cantons.setdefault(vote_id, {})[code] = [y, t]

    def add_municipality(self, vote_id: str, canton: str, bfs, name: str, yes, turnout) -> None:
        y, t = round1(yes), round1(turnout)
        if y is None or canton not in CANTON_BY_CODE:
            return
        m = self.munis[canton]
        m["names"][str(bfs)] = name
        m["results"][vote_id][str(bfs)] = [y, t]

    # -- output --------------------------------------------------------
    def write(self, out: pathlib.Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "municipalities").mkdir(exist_ok=True)
        votes = sorted(self.votes.values(), key=lambda v: (v["date"], v["id"]))
        meta = {
            "built": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "demo": self.demo,
            "sources": sorted(self.sources),
            "voteCount": len(votes),
            "latest": votes[-1]["date"] if votes else None,
        }
        dump = lambda p, obj: p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        dump(out / "votes.json", {"meta": meta, "votes": votes})
        dump(out / "cantons.json", self.cantons)
        for code in list(pathlib.Path(out / "municipalities").glob("*.json")):
            code.unlink()
        for code, m in self.munis.items():
            dump(out / "municipalities" / f"{code}.json",
                 {"names": m["names"], "results": {k: v for k, v in m["results"].items()}})
