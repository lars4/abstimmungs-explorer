# Adding a data source (cantonal, communal, …)

Every source is a function that writes into a `Store` (see `pipeline/store.py`). Nothing else in the project needs to change.

```python
# pipeline/my_canton.py
from .common import get_json
from .store import Store

def load(store: Store) -> int:
    doc = get_json("https://…/results.json")            # 1. fetch
    added = 0
    for p in doc["proposals"]:                            # 2. normalise
        vid = store.next_id(p["date"])                    #    id = YYYYMMDD-n
        store.add_vote(vid, p["date"], {"de": p["title"]},
                       kind="referendum", yes=p["yes_pct"], turnout=p["turnout_pct"],
                       source="Kanton XY OGD")
        for m in p["municipalities"]:
            store.add_municipality(vid, "XY", m["bfs"], m["name"], m["yes_pct"], m["turnout_pct"])
        added += 1
    return added
```

Then register it in `pipeline/build.py` next to `voteinfo.load_missing(...)`.

## Guidelines

- **Dedupe by date**: federal sources must not add dates that already exist (see `voteinfo.load_missing`). Cantonal proposals should use a separate `level` once the UI supports it (open an issue first).
- **Be loud**: raise / `SystemExit` with a helpful message when the schema changes; never write partial data.
- **Test with a fixture**: put a minimal hand-written sample of the source schema in `tests/test_pipeline.py`.
- **Respect the source's terms** and cite it via the `source=` argument (shown on the *Quellen* page).
- Use the opendata.swiss CKAN API (`https://ckan.opendata.swiss/api/3/action/package_show?id=…`) to discover resource URLs instead of hard-coding them.

## Candidate sources

- opendata.swiss: *Echtzeitdaten am Abstimmungstag zu kantonalen Abstimmungsvorlagen*
- Cantonal statistics offices with their own OGD portals (e.g. Zürich, Basel-Stadt, Luzern/LUSTAT, Ticino/Ustat)
- Municipal portals (City of Zürich, Bern, Basel, Luzern, …)
