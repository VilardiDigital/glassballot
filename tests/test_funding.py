import unittest

from pipeline.sources.funding import summarize, sector, committee_kind


def r(t, amt, name="", occ="", addr=None, item="CH"):
    d = {"type": t, "amount": amt, "name": name, "occ": occ, "item": item, "date": "2026-06-15"}
    if addr:
        d["addr"] = addr
    return d


class Funding(unittest.TestCase):
    def test_sectors(self):
        self.assertEqual(sector("Suncoast Cimbora LLC Land Development"), "realestate")
        self.assertEqual(sector("Integrity Mobile Concrete LLC Concrete Contractor"), "construction")
        self.assertEqual(sector("Lowman Law Firm Law Firm"), "law")
        self.assertEqual(sector("Crockett's Towing, LLC"), "towing")
        self.assertIsNone(sector("Mark3 Limited LLC"))

    def test_committees(self):
        self.assertEqual(committee_kind("Realtors Political Advocacy Co"), "industry")
        self.assertEqual(committee_kind("Teamsters Local 79 PAC for Bet"), "union")
        self.assertEqual(committee_kind("Friends Of Judson Sapp"), "politician")
        self.assertEqual(committee_kind("Florida Prosper"), "other")

    def test_private_names_and_misfiled_pacs(self):
        s = summarize([r("B", 250, "Lisa Hopper", "Hopper Pools and Spas", "po 5614"), r("B", 1000, "Realtors pac", "Real Estate Committee")])
        self.assertEqual(s["byGiver"].get("people"), 250)
        self.assertEqual([c["name"] for c in s["committees"]], ["Realtors pac"])
        self.assertFalse(any("Hopper" in n for x in s["sectors"] for n, _ in x["topBusinesses"]))

    def test_summary(self):
        rows = [
            r("B", 1000, "Deeb Construction & Developmen", "Construction Company", "9400 river crossing blvd"),
            r("B", 1000, "The Villas at Seven Hills LTD", "Real Estate", "9400 river crossing blvd"),
            r("B", 1000, "Tri County Development Inc.", "Development Company", "9400 river crossing blvd"),
            r("I", 500, occ="Attorney"), r("I", 200, occ="Retired"), r("I", 100),
            r("F", 1000, "Firefighters For A Better Hern"), r("F", -1000, "Florida Home Builders Pac", item="RE"),
            r("P", 1996, "Florida House Republican Campa", item="IK"), r("S", 3000, item="LO"),
        ]
        s = summarize(rows)
        self.assertEqual(s["total"], 8796)
        self.assertEqual(s["inKind"], 1996)
        self.assertEqual(s["byGiver"]["business"], 3000)
        self.assertEqual(s["byGiver"]["self"], 3000)
        self.assertNotIn("committee", s["byGiver"])  # a refund cancelled the only other committee gift
        self.assertEqual(len(s["sharedAddress"]), 1)
        self.assertEqual(s["sharedAddress"][0]["amount"], 3000)
        ids = {x["id"]: x for x in s["sectors"]}
        self.assertEqual(ids["construction"]["amount"], 1000)
        self.assertEqual(ids["realestate"]["amount"], 2000)
        self.assertEqual(ids["law"]["fromPeople"], 500)
        self.assertEqual([c["name"] for c in s["committees"]], ["Firefighters For A Better Hern…"])
        self.assertEqual(s["committees"][0]["kind"], "publicsafety")


if __name__ == "__main__":
    unittest.main()
