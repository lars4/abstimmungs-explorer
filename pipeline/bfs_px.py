"""BFS PxWeb adapter (historical results).

Tables (published on opendata.swiss by the Federal Statistical Office):
  px-x-1703030000_100   results by canton, since 1866
  px-x-1703030000_101   results by canton / district / municipality, since 1960

The adapter is deliberately generic: it reads the table's variable list, resolves the
roles (vote, canton, municipality, measure) by label, queries in chunks (PxWeb limits the
cell count per request) and parses json-stat2. If BFS renames a variable the run stops
with a message listing what it found - override with --map (see README).
"""
from __future__ import annotations

import itertools
import re
from typing import Iterator

from .common import (CANTON_BY_NUMBER, canton_code, get_json, is_national, post_json,
                     norm_label)
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
    """'18.06.2023 - Klimagesetz' -> ('2023-06-18', 'Klimagesetz')."""
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
    """Find which variable plays which role. Returns {role: variable_dict}."""
    roles: dict[str, dict] = {}
    override = override or {}
    for var in meta["variables"]:
        text = norm_label(var.get("text", "")) + " " + norm_label(var.get("code", ""))
        for role, keys in (
            ("muni", ("gemeinde", "commune")),
            ("canton", ("kanton", "canton")),
            ("vote", ("vorlage", "objet", "abstimmung")),
            ("measure", ("ergebnis", "résultat", "resultat", "indikator", "merkmal")),
        ):
            if role in roles:
                continue
            if override.get(role) == var["code"] or any(k in text for k in keys):
                if role == "canton" and any(k in text for k in ("gemeinde", "commune")):
                    continue
                roles[role] = var
                break
    missing = [r for r in ("vote", "canton", "measure") if r not in roles]
    if missing:
        found = [(v["code"], v["text"]) for v in meta["variables"]]
        raise SystemExit(
            f"Could not resolve variable roles {missing}. Variables found: {found}. "
            f"Pass --map role=CODE (roles: vote, canton, muni, measure)."
        )
    return roles


def pick_measures(var: dict) -> dict[str, str]:
    """Choose the value codes for 'yes share' and 'turnout' within the measure variable."""
    out: dict[str, str] = {}
    for code, text in zip(var["values"], var["valueTexts"]):
        t = norm_label(text)
        if "beteiligung" in t and "turnout" not in out:
            out["turnout"] = code
        elif ("ja" in t.split() or t.startswith("ja")) and ("%" in t or "anteil" in t) and "yes" not in out:
            out["yes"] = code
    if "yes" not in out:
        raise SystemExit(
            "Could not find the 'Ja-Stimmenanteil' measure. Values: "
            + repr(list(zip(var["values"], var["valueTexts"])))
        )
    return out


def query_chunks(meta: dict, roles: dict, measures: dict, chunk_var: dict,
                 max_cells: int, only_values: set[str] | None = None) -> Iterator[dict]:
    """Yield PxWeb POST bodies, splitting `chunk_var` so each request stays under max_cells."""
    sel = {}
    for var in meta["variables"]:
        if var["code"] == roles["measure"]["code"]:
            sel[var["code"]] = list(measures.values())
        else:
            sel[var["code"]] = list(var["values"])
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


def _rows_to_vote_results(rows, roles, measures):
    """Group cells by (vote, area) -> {'yes':..,'turnout':..}."""
    inv = {code: key for key, code in measures.items()}
    grouped: dict[tuple, dict] = {}
    for r in rows:
        measure = inv.get(r[roles["measure"]["code"]][0])
        if not measure:
            continue
        vote = r[roles["vote"]["code"]]
        canton = r[roles["canton"]["code"]]
        muni = r[roles["muni"]["code"]] if "muni" in roles else None
        grouped.setdefault((vote, canton, muni), {})[measure] = r["_value"]
    return grouped


def load_cantons(store: Store, max_cells: int = 20000, since: int | None = None,
                 override: dict | None = None) -> None:
    meta = fetch_table_meta(CANTON_TABLE)
    roles = resolve_roles(meta, override)
    roles.pop("muni", None)
    measures = pick_measures(roles["measure"])
    only = _votes_since(roles["vote"], since)
    ids: dict[str, str] = {}
    for body in query_chunks(meta, roles, measures, roles["vote"], max_cells, only):
        js = post_json(BASE.format(table=CANTON_TABLE), body)
        grouped = _rows_to_vote_results(parse_jsonstat2(js), roles, measures)
        for (vote, canton, _), val in sorted(grouped.items(), key=lambda kv: kv[0][0][1]):
            vcode, vlabel = vote
            date, title = split_vote_label(vlabel)
            if not date:
                continue
            vid = ids.get(vcode)
            if vid is None:
                vid = ids[vcode] = store.next_id(date)
                store.add_vote(vid, date, {"de": title}, source="BFS PxWeb px-x-1703030000_100")
            if is_national(canton[1]):
                v = store.votes[vid]
                v["yes"] = round(float(val.get("yes", 0)), 1) if val.get("yes") is not None else None
                v["turnout"] = round(float(val["turnout"]), 1) if val.get("turnout") is not None else None
                v["accepted"] = v["yes"] is not None and v["yes"] > 50
                continue
            code = canton_code(canton[0]) or canton_code(canton[1])
            if code:
                store.add_canton(vid, code, val.get("yes"), val.get("turnout"))


def load_municipalities(store: Store, max_cells: int = 20000, since: int | None = 1990,
                        override: dict | None = None) -> None:
    meta = fetch_table_meta(MUNI_TABLE)
    roles = resolve_roles(meta, override)
    if "muni" not in roles:
        raise SystemExit("Municipality variable not found in table " + MUNI_TABLE)
    measures = pick_measures(roles["measure"])
    only = _votes_since(roles["vote"], since)
    # Votes must already be known from the canton table: match them by date + title.
    by_key = {(v["date"], v["title"].get("de", "")): v["id"] for v in store.votes.values()}
    by_date: dict[str, list[str]] = {}
    for v in store.votes.values():
        by_date.setdefault(v["date"], []).append(v["id"])
    for body in query_chunks(meta, roles, measures, roles["vote"], max_cells, only):
        js = post_json(BASE.format(table=MUNI_TABLE), body)
        grouped = _rows_to_vote_results(parse_jsonstat2(js), roles, measures)
        for (vote, canton, muni), val in grouped.items():
            date, title = split_vote_label(vote[1])
            vid = by_key.get((date, title))
            if vid is None and len(by_date.get(date, [])) == 1:
                vid = by_date[date][0]  # only one proposal that day: unambiguous
            code = canton_code(canton[0]) or canton_code(canton[1])
            if not (vid and code and muni):
                continue
            m = re.match(r"^\.*\s*(?:0*(\d+))?\s*(.*)$", muni[1])
            bfs = muni[0].lstrip("0") or muni[0]
            name = (m.group(2) if m else muni[1]).strip() or muni[1]
            store.add_municipality(vid, code, bfs, name, val.get("yes"), val.get("turnout"))


def _votes_since(vote_var: dict, since: int | None) -> set[str] | None:
    if not since:
        return None
    keep = set()
    for code, text in zip(vote_var["values"], vote_var["valueTexts"]):
        d = parse_date(text)
        if d is None or int(d[:4]) >= since:
            keep.add(code)
    return keep
