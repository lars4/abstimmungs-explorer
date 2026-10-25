"""BFS PxWeb adapter (historical results).

Tables (published on opendata.swiss by the Federal Statistical Office):
  px-x-1703030000_100   results by canton, since 1866
      variables: 'Kanton' (Schweiz + 26 cantons), 'Datum und Vorlage', 'Ergebnis'
  px-x-1703030000_101   results by canton / district / municipality, since 1960
      variables: ONE hierarchical area variable 'Kanton (-) / Bezirk (>>) / Gemeinde (......)'
                 whose labels are prefixed '- ' (canton), '>> ' (district), '......' (municipality),
                 plus 'Datum und Vorlage' and 'Ergebnis'

Vote labels look like '2026-06-14 Volksinitiative «…»'.

The adapter reads the table's variable list, resolves roles by label, queries in chunks (PxWeb
limits the cell count per request) and parses json-stat2. If BFS renames a variable the run
stops with a message listing what it found - override with --map (see README).
"""
from __future__ import annotations

import difflib
import itertools
import re
from collections import defaultdict
from typing import Iterator

from .common import canton_code, get_json, is_national, norm_label, post_json, round1
from .store import Store

BASE = "https://www.pxweb.bfs.admin.ch/api/v1/de/{table}/{table}.px"
CANTON_TABLE = "px-x-1703030000_100"
MUNI_TABLE = "px-x-1703030000_101"

DATE_RES = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), lambda m: f"{m[1]}-{m[2]}-{m[3]}"),
    (re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})"), lambda m: f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"),
]


def parse_date(label: str) -> str | None:
    for rx, fmt in DATE_RES:
        m = rx.search(label)
        if m:
            return fmt(m)
    return None


def split_vote_label(label: str) -> tuple[str | None, str]:
    """'2023-06-18 Klimagesetz' -> ('2023-06-18', 'Klimagesetz')."""
    date = parse_date(label)
    title = re.sub(r"^\s*(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})\s*[-–:]?\s*", "", label).strip()
    return date, title or label


# --------------------------------------------------------------------------- json-stat2
def parse_jsonstat2(js: dict) -> Iterator[dict]:
    """Yield {dimension_code: (category_code, category_label), ..., '_value': x} per cell."""
    ids, sizes = js["id"], js["size"]
    cats = []
    for dim_id in ids:
        cat = js["dimension"][dim_id]["category"]
        index = cat["index"]
        if isinstance(index, dict):
            order = [k for k, _ in sorted(index.items(), key=lambda kv: kv[1])]
        else:
            order = list(index)
        labels = cat.get("label", {})
        cats.append([(code, labels.get(code, code)) for code in order])
    values = js["value"]
    if isinstance(values, dict):  # sparse form
        values = [values.get(str(i)) for i in range(_prod(sizes))]
    for flat, combo in enumerate(itertools.product(*[range(s) for s in sizes])):
        v = values[flat]
        if v is None:
            continue
        row = {ids[i]: cats[i][combo[i]] for i in range(len(ids))}
        row["_value"] = v
        yield row


def _prod(xs):
    p = 1
    for x in xs:
        p *= x
    return p


# --------------------------------------------------------------------------- PxWeb client
def fetch_table_meta(table: str) -> dict:
    return get_json(BASE.format(table=table))


def resolve_roles(meta: dict, override: dict | None = None) -> dict:
    """Find which variable plays which role.

    Roles: vote, measure, and one of canton (own variable) / area (hierarchical canton-district-
    municipality variable). Returns {role: variable_dict}.
    """
    override = override or {}
    roles: dict[str, dict] = {}
    for var in meta["variables"]:
        text = norm_label(var.get("text", "")) + " " + norm_label(var.get("code", ""))
        has = lambda *keys: any(k in text for k in keys)  # noqa: E731
        role = next((r for r, code in override.items() if code == var["code"]), None)
        if role is None:
            if has("gemeinde", "commune") and has("kanton", "canton"):
                role = "area"
            elif has("kanton", "canton"):
                role = "canton"
            elif has("vorlage", "objet", "abstimmung"):
                role = "vote"
            elif has("ergebnis", "résultat", "resultat", "indikator", "merkmal"):
                role = "measure"
        if role and role not in roles:
            roles[role] = var
    missing = [r for r in ("vote", "measure") if r not in roles]
    if "canton" not in roles and "area" not in roles:
        missing.append("canton")
    if missing:
        found = [(v["code"], v["text"]) for v in meta["variables"]]
        raise SystemExit(
            f"Could not resolve variable roles {missing}. Variables found: {found}. "
            f"Pass --map role=CODE (roles: vote, canton, area, measure)."
        )
    return roles


def pick_measures(var: dict) -> dict[str, str]:
    """Choose the value codes for 'yes share' and 'turnout' within the measure variable."""
    out: dict[str, str] = {}
    for code, text in zip(var["values"], var["valueTexts"]):
        t = norm_label(text)
        if "beteiligung" in t and "turnout" not in out:
            out["turnout"] = code
        elif t.startswith("ja") and not t.startswith("jahr") and ("%" in t or "anteil" in t) and "yes" not in out:
            out["yes"] = code
    if "yes" not in out:
        raise SystemExit(
            "Could not find the yes-share measure ('Ja in %'). Values: "
            + repr(list(zip(var["values"], var["valueTexts"])))
        )
    return out


def area_index(var: dict) -> dict[str, tuple[str, str, str]]:
    """Walk the hierarchical area variable once.

    Returns {value_code: (canton_code, bfs_number, name)} for municipality rows only. Canton rows
    ('- Zürich') set the current canton, district rows ('>> Bezirk …') are skipped, the national
    row ('Schweiz') is skipped.
    """
    out: dict[str, tuple[str, str, str]] = {}
    canton: str | None = None
    for code, text in zip(var["values"], var["valueTexts"]):
        raw = str(text).strip()
        if raw.startswith("."):
            if not canton:
                continue
            m = re.match(r"^\.+\s*(\d+)\s+(.*)$", raw)
            if m:
                bfs, name = m.group(1).lstrip("0") or "0", m.group(2).strip()
            else:  # no number in the label: fall back to the value code
                bfs, name = str(code), raw.lstrip(". ").strip()
            out[code] = (canton, bfs, name)
        elif raw.startswith(">"):
            continue
        elif raw.startswith("-"):
            canton = canton_code(raw)
        else:
            canton = None
    return out


def query_chunks(meta: dict, roles: dict, measures: dict, chunk_var: dict, max_cells: int,
                 only_values: set[str] | None = None, restrict: dict | None = None) -> Iterator[dict]:
    """Yield PxWeb POST bodies, splitting `chunk_var` so each request stays under max_cells.

    `restrict` = {variable_code: [values]} narrows other variables (e.g. municipality rows only).
    """
    sel = {}
    for var in meta["variables"]:
        if var["code"] == roles["measure"]["code"]:
            sel[var["code"]] = list(measures.values())
        else:
            sel[var["code"]] = list((restrict or {}).get(var["code"], var["values"]))
    other = _prod([len(v) for k, v in sel.items() if k != chunk_var["code"]]) or 1
    step = max(1, max_cells // other)
    values = [v for v in chunk_var["values"] if not only_values or v in only_values]
    for i in range(0, len(values), step):
        q = dict(sel)
        q[chunk_var["code"]] = values[i:i + step]
        yield {
            "query": [{"code": c, "selection": {"filter": "item", "values": v}} for c, v in q.items()],
            "response": {"format": "json-stat2"},
        }


def _group(js: dict, roles: dict, measures: dict, area_code: str) -> dict:
    """Group cells by (vote cell, area cell) -> {'yes': x, 'turnout': y}."""
    inv = {code: key for key, code in measures.items()}
    grouped: dict[tuple, dict] = defaultdict(dict)
    for r in parse_jsonstat2(js):
        measure = inv.get(r[roles["measure"]["code"]][0])
        if measure:
            grouped[(r[roles["vote"]["code"]], r[area_code])][measure] = r["_value"]
    return grouped


# --------------------------------------------------------------------------- loaders
def load_cantons(store: Store, max_cells: int = 20000, since: int | None = None,
                 override: dict | None = None) -> None:
    meta = fetch_table_meta(CANTON_TABLE)
    roles = resolve_roles(meta, override)
    area_var = roles.get("canton") or roles["area"]
    measures = pick_measures(roles["measure"])
    only = _votes_since(roles["vote"], since)
    ids: dict[str, str] = {}
    for body in query_chunks(meta, roles, measures, roles["vote"], max_cells, only):
        js = post_json(BASE.format(table=CANTON_TABLE), body)
        grouped = _group(js, roles, measures, area_var["code"])
        for (vote, canton), val in sorted(grouped.items(), key=lambda kv: kv[0][0][1]):
            vcode, vlabel = vote
            date, title = split_vote_label(vlabel)
            if not date:
                continue
            vid = ids.get(vcode)
            if vid is None:
                vid = ids[vcode] = store.next_id(date)
                store.add_vote(vid, date, {"de": title}, source="BFS PxWeb px-x-1703030000_100")
            if is_national(canton[1]) or is_national(canton[0]):
                v = store.votes[vid]
                v["yes"], v["turnout"] = round1(val.get("yes")), round1(val.get("turnout"))
                v["accepted"] = v["yes"] is not None and v["yes"] > 50
                continue
            code = canton_code(canton[1]) or canton_code(canton[0])
            if code:
                store.add_canton(vid, code, val.get("yes"), val.get("turnout"))


def _match_vote(store: Store, by_key: dict, by_date: dict, date: str | None, title: str) -> str | None:
    vid = by_key.get((date, title))
    if vid:
        return vid
    candidates = by_date.get(date, [])
    if len(candidates) == 1:
        return candidates[0][0]  # only one proposal that day: unambiguous
    best = difflib.get_close_matches(title, [t for _, t in candidates], n=1, cutoff=0.6)
    return next((i for i, t in candidates if t == best[0]), None) if best else None


def load_municipalities(store: Store, max_cells: int = 20000, since: int | None = 1990,
                        override: dict | None = None) -> None:
    meta = fetch_table_meta(MUNI_TABLE)
    roles = resolve_roles(meta, override)
    if "area" not in roles:
        raise SystemExit("Hierarchical area variable not found in table " + MUNI_TABLE
                         + f": {[(v['code'], v['text']) for v in meta['variables']]}")
    area = roles["area"]
    index = area_index(area)
    if not index:
        raise SystemExit("No municipality rows recognised in the area variable; sample: "
                         + repr(area["valueTexts"][:8]))
    measures = pick_measures(roles["measure"])
    only = _votes_since(roles["vote"], since)

    by_key = {(v["date"], v["title"].get("de", "")): v["id"] for v in store.votes.values()}
    by_date: dict[str, list[tuple[str, str]]] = {}
    for v in store.votes.values():
        by_date.setdefault(v["date"], []).append((v["id"], v["title"].get("de", "")))

    unmatched = 0
    for body in query_chunks(meta, roles, measures, roles["vote"], max_cells, only,
                             restrict={area["code"]: list(index)}):
        js = post_json(BASE.format(table=MUNI_TABLE), body)
        for (vote, acell), val in _group(js, roles, measures, area["code"]).items():
            info = index.get(acell[0])
            if not info:
                continue
            date, title = split_vote_label(vote[1])
            vid = _match_vote(store, by_key, by_date, date, title)
            if not vid:
                unmatched += 1
                continue
            canton, bfs, name = info
            store.add_municipality(vid, canton, bfs, name, val.get("yes"), val.get("turnout"))
    if unmatched:
        print(f"  note: {unmatched} municipality cells could not be matched to a vote", flush=True)


def _votes_since(vote_var: dict, since: int | None) -> set[str] | None:
    if not since:
        return None
    keep = set()
    for code, text in zip(vote_var["values"], vote_var["valueTexts"]):
        d = parse_date(text)
        if d is None or int(d[:4]) >= since:
            keep.add(code)
    return keep
