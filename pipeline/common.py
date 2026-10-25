"""Shared helpers: HTTP, paths and canton reference data. Standard library only."""
from __future__ import annotations

import json
import pathlib
import re
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "web" / "data"
CACHE_DIR = ROOT / ".cache"
USER_AGENT = "abstimmungs-explorer/0.1 (+https://github.com/lars4/abstimmungs-explorer)"

# code, BFS number, names in de / fr / it (used to resolve labels in source data)
CANTONS = [
    ("ZH", 1, ["Zürich", "Zurich", "Zurigo"]),
    ("BE", 2, ["Bern", "Berne", "Berna", "Bern/Berne"]),
    ("LU", 3, ["Luzern", "Lucerne", "Lucerna"]),
    ("UR", 4, ["Uri"]),
    ("SZ", 5, ["Schwyz", "Svitto"]),
    ("OW", 6, ["Obwalden", "Obwald", "Obvaldo"]),
    ("NW", 7, ["Nidwalden", "Nidwald", "Nidvaldo"]),
    ("GL", 8, ["Glarus", "Glaris", "Glarona"]),
    ("ZG", 9, ["Zug", "Zoug", "Zugo"]),
    ("FR", 10, ["Freiburg", "Fribourg", "Friburgo", "Fribourg/Freiburg"]),
    ("SO", 11, ["Solothurn", "Soleure", "Soletta"]),
    ("BS", 12, ["Basel-Stadt", "Bâle-Ville", "Basilea Città"]),
    ("BL", 13, ["Basel-Landschaft", "Bâle-Campagne", "Basilea Campagna"]),
    ("SH", 14, ["Schaffhausen", "Schaffhouse", "Sciaffusa"]),
    ("AR", 15, ["Appenzell Ausserrhoden", "Appenzell Rhodes-Extérieures", "Appenzello Esterno"]),
    ("AI", 16, ["Appenzell Innerrhoden", "Appenzell Rhodes-Intérieures", "Appenzello Interno"]),
    ("SG", 17, ["St. Gallen", "Saint-Gall", "San Gallo"]),
    ("GR", 18, ["Graubünden", "Grisons", "Grigioni", "Graubünden/Grigioni/Grischun"]),
    ("AG", 19, ["Aargau", "Argovie", "Argovia"]),
    ("TG", 20, ["Thurgau", "Thurgovie", "Turgovia"]),
    ("TI", 21, ["Tessin", "Ticino"]),
    ("VD", 22, ["Waadt", "Vaud"]),
    ("VS", 23, ["Wallis", "Valais", "Vallese", "Valais/Wallis"]),
    ("NE", 24, ["Neuenburg", "Neuchâtel", "Neuchâtel"]),
    ("GE", 25, ["Genf", "Genève", "Ginevra"]),
    ("JU", 26, ["Jura"]),
]
CANTON_BY_CODE = {c[0]: c for c in CANTONS}
CANTON_BY_NUMBER = {c[1]: c[0] for c in CANTONS}
NATIONAL_LABELS = {"schweiz", "suisse", "svizzera", "ch", "switzerland", "total"}


def norm_label(s: str) -> str:
    s = re.sub(r"^[\.\-\s>]+", "", str(s)).strip().lower()
    s = re.sub(r"\s*/\s*", "/", s)  # 'Bern / Berne' -> 'bern/berne'
    s = re.sub(r"\s+", " ", s)
    return s


_CANTON_LOOKUP: dict[str, str] = {}
for _code, _num, _names in CANTONS:
    _CANTON_LOOKUP[_code.lower()] = _code
    _CANTON_LOOKUP[str(_num)] = _code
    for _n in _names:
        _CANTON_LOOKUP[norm_label(_n)] = _code


def canton_code(label_or_code: str | int | None) -> str | None:
    """Resolve a canton label / abbreviation / BFS number to the 2-letter code."""
    if label_or_code is None:
        return None
    key = norm_label(str(label_or_code))
    if key in _CANTON_LOOKUP:
        return _CANTON_LOOKUP[key]
    if "/" in key:  # bilingual labels: try each part ('graubünden/grigioni/grischun')
        for part in key.split("/"):
            if part.strip() in _CANTON_LOOKUP:
                return _CANTON_LOOKUP[part.strip()]
    # labels such as "- Zürich" or "Zürich (ZH)"
    m = re.search(r"\(([A-Za-z]{2})\)", str(label_or_code))
    if m and m.group(1).upper() in CANTON_BY_CODE:
        return m.group(1).upper()
    return None


def is_national(label: str) -> bool:
    return norm_label(label) in NATIONAL_LABELS


def request(url: str, data: bytes | None = None, headers: dict | None = None,
            retries: int = 4, timeout: int = 90) -> bytes:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json, */*"}
    if headers:
        hdrs.update(headers)
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt * 2)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Request failed after {retries} attempts: {url}: {last}")


def get_json(url: str, **kw):
    return json.loads(request(url, **kw).decode("utf-8-sig"))


def post_json(url: str, payload: dict, **kw):
    body = json.dumps(payload).encode("utf-8")
    return json.loads(
        request(url, data=body, headers={"Content-Type": "application/json"}, **kw).decode("utf-8-sig")
    )


def round1(x) -> float | None:
    try:
        return None if x is None else round(float(x), 1)
    except (TypeError, ValueError):
        return None
