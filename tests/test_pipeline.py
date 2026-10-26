"""Offline tests for the pipeline using hand-written fixtures that mimic the source schemas.

The fixtures are NOT real data; they only pin down the parsing logic. Real-source drift is
caught by the weekly `update-data` workflow, which fails loudly instead of overwriting data.
"""
import itertools
import json
import pathlib
import tempfile
import unittest
import urllib.error
from unittest import mock

from pipeline import bfs_px, common, demo, voteinfo
from pipeline.common import canton_code, is_national
from pipeline.store import Store

JSONSTAT = {
    "id": ["Vorlage", "Kanton", "Ergebnis"],
    "size": [1, 3, 2],
    "dimension": {
        "Vorlage": {"category": {"index": {"v1": 0}, "label": {"v1": "18.06.2023 - Klimagesetz (Beispiel)"}}},
        "Kanton": {"category": {"index": {"0": 0, "1": 1, "25": 2},
                                "label": {"0": "Schweiz", "1": "Zürich", "25": "Genf"}}},
        "Ergebnis": {"category": {"index": {"yes": 0, "turn": 1},
                                  "label": {"yes": "Ja-Stimmenanteil (%)", "turn": "Stimmbeteiligung (%)"}}},
    },
    "value": [59.1, 42.0, 61.2, 44.5, 55.0, 41.1],
}

META = {"variables": [
    {"code": "Vorlage", "text": "Abstimmungsvorlage", "values": ["v1"], "valueTexts": ["18.06.2023 - Klimagesetz (Beispiel)"]},
    {"code": "Kanton", "text": "Kanton", "values": ["0", "1", "25"], "valueTexts": ["Schweiz", "Zürich", "Genf"]},
    {"code": "Ergebnis", "text": "Ergebnis", "values": ["yes", "turn", "n"],
     "valueTexts": ["Ja-Stimmenanteil (%)", "Stimmbeteiligung (%)", "Stimmberechtigte"]},
]}


class Common(unittest.TestCase):
    def test_canton_lookup(self):
        self.assertEqual(canton_code("Zürich"), "ZH")
        self.assertEqual(canton_code("  - Genève"), "GE")
        self.assertEqual(canton_code("Bern/Berne"), "BE")
        self.assertEqual(canton_code(25), "GE")
        self.assertEqual(canton_code("Atlantis"), None)
        self.assertTrue(is_national("Schweiz"))
        self.assertFalse(is_national("Zürich"))


class BfsPx(unittest.TestCase):
    def test_parse_jsonstat2(self):
        rows = list(bfs_px.parse_jsonstat2(JSONSTAT))
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["Kanton"], ("0", "Schweiz"))
        self.assertEqual(rows[0]["_value"], 59.1)
        self.assertEqual(rows[5]["Kanton"], ("25", "Genf"))
        self.assertEqual(rows[5]["Ergebnis"][0], "turn")

    def test_roles_and_measures(self):
        roles = bfs_px.resolve_roles(META)
        self.assertEqual({k: v["code"] for k, v in roles.items()},
                         {"vote": "Vorlage", "canton": "Kanton", "measure": "Ergebnis"})
        self.assertEqual(bfs_px.pick_measures(roles["measure"]), {"turnout": "turn", "yes": "yes"})

    def test_unresolvable_roles_give_helpful_error(self):
        with self.assertRaises(SystemExit) as cm:
            bfs_px.resolve_roles({"variables": [{"code": "X", "text": "Foo", "values": [], "valueTexts": []}]})
        self.assertIn("--map", str(cm.exception))

    def test_chunking_respects_cell_limit(self):
        roles = bfs_px.resolve_roles(META)
        meta = json.loads(json.dumps(META))
        meta["variables"][0]["values"] = [f"v{i}" for i in range(10)]
        roles["vote"] = meta["variables"][0]
        measures = bfs_px.pick_measures(roles["measure"])
        bodies = list(bfs_px.query_chunks(meta, roles, measures, roles["vote"], max_cells=12))
        per = [len(next(q for q in b["query"] if q["code"] == "Vorlage")["selection"]["values"]) for b in bodies]
        self.assertEqual(sum(per), 10)
        self.assertTrue(all(n * 3 * 2 <= 12 for n in per))  # 3 cantons x 2 measures

    def test_vote_label_and_dates(self):
        self.assertEqual(bfs_px.split_vote_label("18.06.2023 - Klimagesetz"), ("2023-06-18", "Klimagesetz"))
        self.assertEqual(bfs_px.split_vote_label("2023-06-18 Klimagesetz")[0], "2023-06-18")
        self.assertEqual(bfs_px.parse_date("keine Angabe"), None)


VOTEINFO = {
    "abstimmtag": "20230618",
    "schweiz": {"vorlagen": [{
        "vorlagenId": 6310, "vorlagenArt": 1,
        "vorlagenTitel": [{"langKey": "de", "text": "Beispielvorlage"}, {"langKey": "fr", "text": "Objet exemple"}],
        "resultat": {"jaStimmenInProzent": 59.14, "stimmbeteiligungInProzent": 42.0, "angenommen": True},
        "kantone": [{"geoLevelnummer": "1", "geoLevelname": "Zürich",
                     "resultat": {"jaStimmenInProzent": 61.2, "stimmbeteiligungInProzent": 44.5},
                     "gemeinden": [{"geoLevelnummer": "261", "geoLevelname": "Zürich",
                                    "resultat": {"jaStimmenInProzent": 70.3, "stimmbeteiligungInProzent": 50.1}},
                                   {"geoLevelnummer": "1", "geoLevelname": "Aeugst am Albis",
                                    "resultat": {"jaStimmenInProzent": None}}]}],
    }]},
}


class VoteInfo(unittest.TestCase):
    def test_ingest(self):
        s = Store()
        self.assertEqual(voteinfo.ingest(s, VOTEINFO), 1)
        v = s.votes["20230618-1"]
        self.assertEqual((v["yes"], v["turnout"], v["accepted"]), (59.1, 42.0, True))
        self.assertEqual(v["title"]["fr"], "Objet exemple")
        self.assertEqual(s.cantons["20230618-1"]["ZH"], [61.2, 44.5])
        self.assertEqual(s.munis["ZH"]["results"]["20230618-1"], {"261": [70.3, 50.1]})  # None yes skipped
        self.assertEqual(s.munis["ZH"]["names"]["261"], "Zürich")

    def test_resource_date(self):
        self.assertEqual(voteinfo.resource_date({"url": "https://x/sd-t-17-02-20240303-eidgAbstimmung.json"}), "2024-03-03")
        self.assertEqual(voteinfo.resource_date({"name": "Abstimmung vom 03.03.2024"}), "2024-03-03")
        self.assertIsNone(voteinfo.resource_date({"url": "https://x/foo.json"}))


# --- fixtures shaped like the REAL BFS tables (variable names/labels taken from `pipeline.build inspect`) ---
MEASURES = ["Stimmberechtigte", "Abgegebene Stimmen", "Beteiligung in %", "Ja", "Nein", "Ja in %", "Nein in %"]
VOTES = ["2026-06-14 Volksinitiative «Beispiel A»", "2026-06-14 Änderung des Beispielgesetzes", "2023-06-18 Klimagesetz"]
REAL_CANTON_META = {"title": "Volksabstimmungen (Ergebnisse Ebene Kanton seit 1866)", "variables": [
    {"code": "Kanton", "text": "Kanton", "values": ["0", "1", "2", "10", "18"],
     "valueTexts": ["Schweiz", "Zürich", "Bern / Berne", "Freiburg / Fribourg", "Graubünden / Grigioni / Grischun"]},
    {"code": "Datum und Vorlage", "text": "Datum und Vorlage", "values": ["v1", "v2", "v3"], "valueTexts": VOTES},
    {"code": "Ergebnis", "text": "Ergebnis", "values": [str(i) for i in range(7)], "valueTexts": MEASURES},
]}
AREAS = ["Schweiz", "- Zürich", ">> Bezirk Affoltern", "...... 1 Aeugst am Albis", "...... 2 Affoltern am Albis",
         "- Bern / Berne", ">> Verwaltungskreis Bern-Mittelland", "......0351 Bern", "- Graubünden / Grigioni / Grischun",
         ">> Region Albula", "......3506 Albula/Alvra"]
REAL_MUNI_META = {"title": "Volksabstimmungen (Ergebnisse Ebene Gemeinde seit 1960)", "variables": [
    {"code": "Kanton (-) / Bezirk (>>) / Gemeinde (......)", "text": "Kanton (-) / Bezirk (>>) / Gemeinde (......)",
     "values": [f"a{i}" for i in range(len(AREAS))], "valueTexts": AREAS},
    {"code": "Datum und Vorlage", "text": "Datum und Vorlage", "values": ["v1", "v2", "v3"], "valueTexts": VOTES},
    {"code": "Ergebnis", "text": "Ergebnis", "values": [str(i) for i in range(7)], "valueTexts": MEASURES},
]}


def fake_pxweb(meta, value_fn):
    """Return a post_json replacement that answers any query with json-stat2 built from `value_fn(coords)`."""
    ids = [v["code"] for v in meta["variables"]]
    texts = {v["code"]: dict(zip(v["values"], v["valueTexts"])) for v in meta["variables"]}

    def post(url, body, **kw):
        sel = {q["code"]: q["selection"]["values"] for q in body["query"]}
        assert body["response"]["format"] == "json-stat2"
        return {
            "id": ids, "size": [len(sel[i]) for i in ids],
            "dimension": {i: {"category": {"index": {c: n for n, c in enumerate(sel[i])},
                                           "label": {c: texts[i][c] for c in sel[i]}}} for i in ids},
            "value": [value_fn(dict(zip(ids, combo))) for combo in itertools.product(*[sel[i] for i in ids])],
        }
    return post


class RealLayout(unittest.TestCase):
    def test_roles_for_real_tables(self):
        c = bfs_px.resolve_roles(REAL_CANTON_META)
        self.assertEqual({k: v["code"] for k, v in c.items()},
                         {"canton": "Kanton", "vote": "Datum und Vorlage", "measure": "Ergebnis"})
        m = bfs_px.resolve_roles(REAL_MUNI_META)
        self.assertEqual(set(m), {"area", "vote", "measure"})
        self.assertEqual(bfs_px.pick_measures(m["measure"]), {"turnout": "2", "yes": "5"})

    def test_area_index_walks_hierarchy(self):
        idx = bfs_px.area_index(REAL_MUNI_META["variables"][0])
        self.assertEqual(idx["a3"], ("ZH", "1", "Aeugst am Albis"))
        self.assertEqual(idx["a7"], ("BE", "351", "Bern"))           # leading zeros stripped
        self.assertEqual(idx["a10"], ("GR", "3506", "Albula/Alvra"))
        self.assertEqual(len(idx), 4)                                  # no districts, no cantons, no Schweiz

    def test_canton_labels_with_slashes(self):
        for label, code in [("Bern / Berne", "BE"), ("- Freiburg / Fribourg", "FR"),
                            ("Graubünden / Grigioni / Grischun", "GR"), ("- Wallis / Valais", "VS")]:
            self.assertEqual(canton_code(label), code)

    def test_end_to_end_with_mocked_server(self):
        def canton_value(c):
            return {"2": 41.5, "5": 52.0 if c["Kanton"] == "0" else 60.0 + int(c["Kanton"]) % 7}.get(c["Ergebnis"], 1000)

        def muni_value(c):
            return {"2": 55.0, "5": 48.0 + int(c["Kanton (-) / Bezirk (>>) / Gemeinde (......)"][1:])}.get(c["Ergebnis"], 10)

        store = Store()
        metas = {bfs_px.CANTON_TABLE: REAL_CANTON_META, bfs_px.MUNI_TABLE: REAL_MUNI_META}
        with mock.patch.object(bfs_px, "fetch_table_meta", side_effect=lambda t: metas[t]):
            with mock.patch.object(bfs_px, "post_json", side_effect=fake_pxweb(REAL_CANTON_META, canton_value)):
                bfs_px.load_cantons(store, max_cells=10)  # tiny limit forces chunking
            with mock.patch.object(bfs_px, "post_json", side_effect=fake_pxweb(REAL_MUNI_META, muni_value)):
                bfs_px.load_municipalities(store, max_cells=40, since=None)

        self.assertEqual(sorted(store.votes), ["20230618-1", "20260614-1", "20260614-2"])
        klima = next(v for v in store.votes.values() if v["date"] == "2023-06-18")
        self.assertEqual((klima["yes"], klima["turnout"], klima["accepted"]), (52.0, 41.5, True))
        self.assertEqual(klima["title"]["de"], "Klimagesetz")
        cants = store.cantons[klima["id"]]
        self.assertEqual(set(cants), {"ZH", "BE", "FR", "GR"})   # slash labels resolved, 'Schweiz' excluded
        munis = store.munis["ZH"]["results"][klima["id"]]
        self.assertEqual(set(munis), {"1", "2"})
        self.assertEqual(store.munis["BE"]["names"]["351"], "Bern")
        self.assertEqual(store.munis["GR"]["names"]["3506"], "Albula/Alvra")
        # every one of the 3 votes has results for all 4 municipalities (title matching worked per date)
        for v in store.votes.values():
            self.assertEqual(sum(len(store.munis[c]["results"][v["id"]]) for c in ("ZH", "BE", "GR")), 4)

    def test_unknown_layout_error_is_helpful(self):
        meta = json.loads(json.dumps(REAL_MUNI_META))
        meta["variables"][0]["valueTexts"] = ["Schweiz"] * len(meta["variables"][0]["values"])
        with mock.patch.object(bfs_px, "fetch_table_meta", return_value=meta):
            with self.assertRaises(SystemExit) as cm:
                bfs_px.load_municipalities(Store())
        self.assertIn("No municipality rows recognised", str(cm.exception))



class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body
    def read(self):
        return self.body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class RateLimiting(unittest.TestCase):
    def test_429_waits_retry_after_then_succeeds(self):
        calls, sleeps = [], []

        def urlopen(req, timeout=0):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {"Retry-After": "7"}, None)
            return FakeResponse(b'{"ok": true}')

        with mock.patch.object(common.urllib.request, "urlopen", urlopen), \
             mock.patch.object(common.time, "sleep", side_effect=sleeps.append), \
             mock.patch.object(common, "MIN_INTERVAL", 0), mock.patch("sys.stderr"):
            self.assertEqual(common.get_json("https://example.invalid/x"), {"ok": True})
        self.assertEqual(len(calls), 2)
        self.assertIn(7.0, sleeps)

    def test_429_without_header_backs_off_and_gives_up(self):
        sleeps = []

        def urlopen(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

        with mock.patch.object(common.urllib.request, "urlopen", urlopen), \
             mock.patch.object(common.time, "sleep", side_effect=sleeps.append), \
             mock.patch.object(common, "MIN_INTERVAL", 0), mock.patch("sys.stderr"):
            with self.assertRaises(RuntimeError):
                common.get_json("https://example.invalid/x", retries=4)
        self.assertEqual([x for x in sleeps if x >= 5], [5.0, 10.0, 20.0, 40.0])

    def test_non_retryable_error_is_raised_immediately(self):
        def urlopen(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        with mock.patch.object(common.urllib.request, "urlopen", urlopen), mock.patch.object(common, "MIN_INTERVAL", 0):
            with self.assertRaises(urllib.error.HTTPError):
                common.get_json("https://example.invalid/x")

    def test_chunk_size_is_halved_when_server_rejects(self):
        meta = json.loads(json.dumps(REAL_CANTON_META))
        n = 600
        meta["variables"][1]["values"] = [f"v{i}" for i in range(n)]
        meta["variables"][1]["valueTexts"] = [f"2000-01-{1 + i % 28:02d} Vorlage {i}" for i in range(n)]
        roles = bfs_px.resolve_roles(meta)
        measures = bfs_px.pick_measures(roles["measure"])
        inner = fake_pxweb(meta, lambda c: 1.0)
        sizes = []

        def limited(url, body, **kw):
            cells = 1
            for q in body["query"]:
                cells *= len(q["selection"]["values"])
            sizes.append(cells)
            if cells > 3000:
                raise urllib.error.HTTPError(url, 403, "too many values", {}, None)
            return inner(url, body)

        with mock.patch.object(bfs_px, "post_json", limited), mock.patch("sys.stderr"):
            responses = list(bfs_px._post_chunks("https://example.invalid/t", meta, roles, measures, 16000))
        covered = sum(r["size"][1] for r in responses)       # vote dimension is the 2nd dimension
        self.assertEqual(covered, n)                          # every vote fetched exactly once
        self.assertEqual(len(responses), 3)                   # 200 + 200 + 200 votes after halving
        self.assertGreater(len(sizes), len(responses))        # rejected attempts happened first


class StoreAndDemo(unittest.TestCase):
    def test_roundtrip(self):
        s = Store()
        demo.generate(s, first_year=2020, last_year=2021)
        self.assertTrue(s.demo and s.votes)
        with tempfile.TemporaryDirectory() as d:
            s.write(pathlib.Path(d))
            votes = json.loads((pathlib.Path(d) / "votes.json").read_text())
            self.assertTrue(votes["meta"]["demo"])
            cantons = json.loads((pathlib.Path(d) / "cantons.json").read_text())
            for v in votes["votes"]:
                self.assertEqual(len(cantons[v["id"]]), 26)
            self.assertTrue(list((pathlib.Path(d) / "municipalities").glob("*.json")))

    def test_demo_is_deterministic(self):
        a, b = Store(), Store()
        demo.generate(a, first_year=2020, last_year=2020)
        demo.generate(b, first_year=2020, last_year=2020)
        self.assertEqual(a.votes, b.votes)
        self.assertEqual(a.cantons, b.cantons)

    def test_unique_ids_per_date(self):
        s = Store()
        s.add_vote(s.next_id("2024-03-03"), "2024-03-03", {"de": "a"})
        s.add_vote(s.next_id("2024-03-03"), "2024-03-03", {"de": "b"})
        self.assertEqual(sorted(s.votes), ["20240303-1", "20240303-2"])


if __name__ == "__main__":
    unittest.main()
