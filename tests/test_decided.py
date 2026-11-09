import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DecidedSeats(unittest.TestCase):
    def test_overrides_point_at_real_races_and_sources(self):
        d = json.loads((ROOT / "data" / "decided_2026.json").read_text())["counties"]
        for county, x in d.items():
            seed = json.loads((ROOT / "data" / f"seed_{county}.json").read_text())
            ids = {r["id"] for r in seed["races"]}
            self.assertEqual(x["source"]["tier"], 1, county)
            self.assertTrue(x["source"]["url"].startswith("https://"), county)
            for rid, v in x["races"].items():
                self.assertIn(rid, ids, f"{county} {rid}")
                self.assertTrue(v["decided"] and v["detail"], f"{county} {rid}")

    def test_apply_marks_race_off_the_november_ballot(self):
        from pipeline.bootstrap import apply_decided
        seed = {"sources": {}, "races": [{"id": "bcc-d2", "sources": ["soe-vf"], "onNovBallot": True}]}
        apply_decided("dixie", seed)
        r = seed["races"][0]
        self.assertIs(r["onNovBallot"], False)
        self.assertIn("enr-2026p", r["sources"])
        self.assertIn("enr-2026p", seed["sources"])


if __name__ == "__main__":
    unittest.main()
