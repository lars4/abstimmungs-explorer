"""Synthetic demo data so the web app can be developed and tested without network access.

EVERYTHING produced here is invented. It is flagged `demo: true` in votes.json and the web
app shows a banner. Never publish demo data as if it were real results.
"""
from __future__ import annotations

import datetime as dt
import math
import random

from .common import CANTONS
from .store import Store

# crude fictional "profiles": language region / urbanity drive the synthetic swing
PROFILE = {
    "urban": ["ZH", "BS", "GE", "VD", "BE", "NE", "ZG", "BL"],
    "rural": ["UR", "SZ", "OW", "NW", "GL", "AI", "AR", "TG", "SG", "SH", "AG", "SO", "LU"],
    "latin": ["VD", "GE", "NE", "JU", "FR", "VS", "TI"],
}

DEMO_TOPICS = ["Verkehr", "Gesundheit", "Steuern", "Energie", "Umwelt", "Bildung", "Migration",
               "Landwirtschaft", "Digitalisierung", "Wohnen"]


def generate(store: Store, seed: int = 7, first_year: int = 2008, last_year: int = 2026) -> None:
    rng = random.Random(seed)
    store.demo = True
    store.sources.add("SYNTHETIC DEMO DATA")
    for year in range(first_year, last_year + 1):
        for month in (3, 6, 9, 11):
            day = dt.date(year, month, 1)
            while day.weekday() != 6:
                day += dt.timedelta(days=1)
            day += dt.timedelta(days=14)
            if day > dt.date(2026, 10, 25):
                continue
            for k in range(rng.choice([1, 2, 3])):
                _one_vote(store, rng, day.isoformat(), k)


def _one_vote(store: Store, rng: random.Random, date: str, k: int) -> None:
    topic = rng.choice(DEMO_TOPICS)
    base = rng.uniform(32, 68)
    urban_bias = rng.uniform(-14, 14)
    latin_bias = rng.uniform(-12, 12)
    vid = store.next_id(date)
    seats = {}
    for code, _num, _names in CANTONS:
        y = base + rng.gauss(0, 3)
        if code in PROFILE["urban"]:
            y += urban_bias
        if code in PROFILE["latin"]:
            y += latin_bias
        y = min(92, max(8, y))
        t = min(80, max(30, 45 + 10 * math.sin(len(date)) + rng.gauss(0, 5) + (4 if code in PROFILE["urban"] else 0)))
        seats[code] = (y, t)
    weights = {c: 1 + (2 if c in PROFILE["urban"] else 0) + rng.random() for c in seats}
    ysum = sum(seats[c][0] * weights[c] for c in seats) / sum(weights.values())
    tsum = sum(seats[c][1] * weights[c] for c in seats) / sum(weights.values())
    kind = rng.choice(["initiative", "referendum", "referendum"])
    store.add_vote(vid, date, {"de": f"DEMO · {topic} ({kind}) {date}", "en": f"DEMO · {topic}"},
                   kind=kind, yes=ysum, turnout=tsum)
    for code, (y, t) in seats.items():
        store.add_canton(vid, code, y, t)
        # ~8 synthetic municipalities per canton, ids are fake
        for i in range(8):
            h = (sum(map(ord, code)) % 997) * 100 + i  # deterministic fake id
            store.add_municipality(vid, code, h, f"Demo-Gemeinde {code}-{i + 1}",
                                   y + rng.gauss(0, 7) + (3 if i % 3 == 0 else -1), t + rng.gauss(0, 4))
