"""BFS real-time / archive adapter (opendata.swiss "Echtzeitdaten am Abstimmungstag").

The dataset lists one JSON resource per vote Sunday (archive back to 1981, municipality
level). Resource URLs are discovered through the opendata.swiss CKAN API so nothing is
hard-coded. Only vote dates that are *not yet* in the store are added, i.e. this fills the
gap between the last release of the BFS PxWeb tables and the latest vote Sunday.
"""
from __future__ import annotations

import re

from .common import CANTON_BY_NUMBER, canton_code, get_json
from .store import Store

CKAN = "https://ckan.opendata.swiss/api/3/action/package_show?id={id}"
DATASET_ID = "echtzeitdaten-am-abstimmungstag-zu-eidgenoessischen-abstimmungsvorlagen"
SOURCE = "BFS opendata.swiss Echtzeitdaten Abstimmungstag"


def list_resources() -> list[dict]:
    pkg = get_json(CKAN.format(id=DATASET_ID))["result"]
    return [r for r in pkg.get("resources", []) if str(r.get("format", "")).upper() == "JSON"]


def resource_date(res: dict) -> str | None:
    text = " ".join(str(res.get(k, "")) for k in ("url", "download_url", "name", "title"))
    m = re.search(r"(20\d{6}|19\d{6})", text)
    if m:
        s = m.group(1)
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    return f"{m[3]}-{m[2]}-{m[1]}" if m else None


def pick_lang(titles, lang: str = "de") -> str:
    if isinstance(titles, str):
        return titles
    for t in titles or []:
        if t.get("langKey") == lang and t.get("text"):
            return t["text"]
    return (titles or [{}])[0].get("text", "")


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def ingest(store: Store, doc: dict, date: str | None = None, municipalities: bool = True) -> int:
    """Normalise one vote-Sunday document into the store. Returns number of proposals added."""
    date = date or _doc_date(doc)
    if not date:
        return 0
    schweiz = doc.get("schweiz") or doc
    added = 0
    for v in schweiz.get("vorlagen", []):
        res = v.get("resultat", {}) or {}
        vid = store.next_id(date)
        kind = v.get("vorlagenArt") or v.get("vorlagenArtId")
        store.add_vote(
            vid, date, {"de": pick_lang(v.get("vorlagenTitel"), "de"),
                        "fr": pick_lang(v.get("vorlagenTitel"), "fr")},
            kind=str(kind) if kind is not None else None,
            yes=num(res.get("jaStimmenInProzent")), turnout=num(res.get("stimmbeteiligungInProzent")),
            accepted=res.get("angenommen"), source=SOURCE)
        for k in v.get("kantone", []):
            code = CANTON_BY_NUMBER.get(int(k.get("geoLevelnummer", 0) or 0)) or canton_code(k.get("geoLevelname"))
            kres = k.get("resultat", {}) or {}
            if code:
                store.add_canton(vid, code, num(kres.get("jaStimmenInProzent")),
                                 num(kres.get("stimmbeteiligungInProzent")))
            if not (municipalities and code):
                continue
            for g in k.get("gemeinden", []):
                gres = g.get("resultat", {}) or {}
                store.add_municipality(vid, code, g.get("geoLevelnummer"), g.get("geoLevelname", ""),
                                       num(gres.get("jaStimmenInProzent")),
                                       num(gres.get("stimmbeteiligungInProzent")))
        added += 1
    return added


def _doc_date(doc: dict) -> str | None:
    s = str(doc.get("abstimmtag") or doc.get("abstimmungstag") or "")
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else None


def load_missing(store: Store, municipalities: bool = True) -> int:
    known = store.dates()
    total = 0
    for res in sorted(list_resources(), key=lambda r: resource_date(r) or ""):
        date = resource_date(res)
        if not date or date in known:
            continue
        url = res.get("download_url") or res.get("url")
        if not url:
            continue
        total += ingest(store, get_json(url), date, municipalities)
    return total
