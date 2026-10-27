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


if __name__ == "__main__":
    unittest.main()
