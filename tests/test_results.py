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


if __name__ == "__main__":
    unittest.main()
