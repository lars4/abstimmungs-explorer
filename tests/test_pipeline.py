"""Offline tests for the pipeline using hand-written fixtures that mimic the source schemas.

The fixtures are NOT real data; they only pin down the parsing logic. Real-source drift is
caught by the weekly `update-data` workflow, which fails loudly instead of overwriting data.
"""
import json
import pathlib
import tempfile
import unittest

from pipeline import bfs_px, demo, voteinfo
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
