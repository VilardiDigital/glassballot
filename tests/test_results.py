import unittest
from pathlib import Path

from pipeline.sources.results import parse, _key


class Results(unittest.TestCase):
    def test_parse(self):
        r = parse((Path(__file__).parent / "fixtures" / "enr_sample.html").read_text())
        self.assertEqual(r["status"], "official")
        self.assertEqual([x["office"] for x in r["races"]], ["County Commissioner, District 3", "School Board, District 4"])
        a = r["races"][0]
        self.assertEqual((a["reported"], a["precincts"]), (32, 32))
        self.assertEqual(a["candidates"][0], {"name": "John Allocco", "party": "REP", "pct": 64.91, "votes": 68729})
        self.assertEqual(a["candidates"][1]["name"], "Luciano S. Vignali")
        b = r["races"][1]
        self.assertEqual((b["reported"], b["precincts"]), (12, 32))
        self.assertEqual(b["candidates"][0]["votes"], 51229)

    def test_keys(self):
        self.assertEqual(_key("County Commissioner, District 3"), ("bcc", "3"))
        self.assertEqual(_key("School Board, District 4"), ("sb", "4"))
        self.assertIsNone(_key("Clerk of Circuit Court"))
        self.assertEqual(_key("Board of County Commissioners District 6 - Single Member"), ("bcc", "6"))
        self.assertEqual(_key("Board of County Commissioners District 2 - At Large"), ("bcc", "2"))
        self.assertIsNone(_key("Referendum on single member county commission districts"))




class ClarityTest(unittest.TestCase):
    def setUp(self):
        import json
        from pathlib import Path
        from pipeline.sources.results import parse_clarity
        self.res = parse_clarity(json.loads((Path(__file__).parent / "fixtures" / "clarity_sum.json").read_text()))

    def test_races(self):
        r = {x["office"]: x for x in self.res["races"]}
        bcc = r["Board of County Commissioners - District 4 - Single"]
        self.assertEqual((bcc["reported"], bcc["precincts"]), (40, 62))
        self.assertEqual(bcc["candidates"][0], {"name": "Dave Eggers", "party": "REP", "pct": 78.51, "votes": 35071})
        self.assertIsNone(r["School Board Member - District 2 - At Large"]["candidates"][0]["party"])
        self.assertEqual(self.res["status"], "unofficial")

    def test_keys(self):
        from pipeline.sources.results import _key
        self.assertEqual(_key("Board of County Commissioners - District 4 - Single"), ("bcc", "4"))
        self.assertEqual(_key("School Board Member - District 2 - At Large"), ("sb", "2"))
        self.assertIsNone(_key("REP United States Senator"))

    def test_find_general(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
        from probe_clarity import find_general
        self.assertEqual(find_general([{"EID": "126780", "Name": "2026 Primary Election", "Date": "08/18/2026"},
                                       {"EID": "128001", "Name": "2026 General Election", "Date": "11/03/2026"}]), 128001)
        self.assertIsNone(find_general([]))

class KeyTest(unittest.TestCase):
    def test_strict(self):
        from pipeline.sources.results import _key
        ok = {"County Commissioner, District 4": ("bcc", "4"), "Board of County Commissioners - District 4": ("bcc", "4"),
              "County Commissioner, At Large, Group 2": ("bcc", "2"), "School Board Member, Dist. 5": ("sb", "5"),
              "School Board  - District 5": ("sb", "5"), "County Commissioner, Dist 2": ("bcc", "2")}
        for o, k in ok.items():
            self.assertEqual(_key(o), k, o)
        for o in ["Commissioner of Agriculture", "Brooksville City Council Member, Seat 1", "Port St. Lucie City Council District 1",
                  "Pasco School Board Millage", "School Board Resolution 2026-02", "Wakulla County School Board  Referendum No. 2026-35",
                  "Single Member Districts for County Commissioners", "CntyChatAmdt Residency County Commissioner", "Arcadia City Council",
                  "City of Crystal River - City Council - Seat 2", "REP United States Senator", "1/2 Cent Surtax Gulf School Bd"]:
            self.assertIsNone(_key(o), o)


if __name__ == "__main__":
    unittest.main()


class ClarityNames(unittest.TestCase):
    def test_party_prefix_is_removed_from_names(self):
        from pipeline.sources.results import parse_clarity
        r = parse_clarity({"Contests": [{"C": "Board of County Commissioners District 2 - At Large", "CH": ["REP Brian Scott", "DEM Tim Hughes"],
                                         "P": ["REP", "DEM"], "V": [195523, 199639], "PCT": [49.48, 50.52], "PR": 288, "TP": 288}]})
        self.assertEqual([c["name"] for c in r["races"][0]["candidates"]], ["Brian Scott", "Tim Hughes"])
        self.assertEqual(r["races"][0]["candidates"][0]["party"], "REP")

    def test_nonpartisan_names_are_untouched(self):
        from pipeline.sources.results import parse_clarity
        r = parse_clarity({"Contests": [{"C": "School Board Member District 3 - At Large", "CH": ["Curtis Campogni", "Dawn Peters"],
                                         "P": ["", ""], "V": [175434, 174722], "PCT": [50.1, 49.9], "PR": 288, "TP": 288}]})
        self.assertEqual([c["name"] for c in r["races"][0]["candidates"]], ["Curtis Campogni", "Dawn Peters"])


class Seating(unittest.TestCase):
    def seed(self, status="official"):
        return {"county": {"termStart": {"commission": {"date": "2026-11-17"}}},
                "people": [{"id": "a", "status": "incumbent", "office": "County Commissioner", "contact": {"phone": "1"}},
                           {"id": "b", "status": "challenger", "office": "Candidate, County Commission"}],
                "races": [{"id": "bcc-d2", "people": ["a", "b"], "results": {"status": status, "counted": True, "leader": "b", "source": "x"}}]}

    def test_certified_winner_is_seated_on_term_start(self):
        from pipeline.sources.results import seat_winners
        s = seat_winners(self.seed(), "2026-11-17")
        p = {x["id"]: x for x in s["people"]}
        self.assertEqual((p["b"]["status"], p["b"]["office"]), ("incumbent", "County Commissioner"))
        self.assertEqual(p["a"]["status"], "former")
        self.assertNotIn("contact", p["a"])

    def test_nothing_changes_before_term_start_or_without_certification(self):
        from pipeline.sources.results import seat_winners
        for seed, day in ((self.seed(), "2026-11-16"), (self.seed("unofficial"), "2026-12-01")):
            p = {x["id"]: x for x in seat_winners(seed, day)["people"]}
            self.assertEqual((p["a"]["status"], p["b"]["status"]), ("incumbent", "challenger"))


class PartyPrefix(unittest.TestCase):
    def test_split(self):
        from pipeline.sources.results import _split_party
        self.assertEqual(_split_party("REP Walter Shea DeLoach", "REP"), ("Walter Shea DeLoach", "REP"))
        self.assertEqual(_split_party("DEM Stefan Blue", None), ("Stefan Blue", "DEM"))
        self.assertEqual(_split_party("Write-in", None), ("Write-in", None))
        self.assertEqual(_split_party("Repp Smith", None), ("Repp Smith", None))
