"""The packaged site: every page has its own address, title and readable summary."""
import json
import re
import unittest
from pathlib import Path

from pipeline.dist import build_dist, page_meta, pages
from pipeline.sources.legistar_summary import auto_headline

ROOT = Path(__file__).resolve().parents[1]


class AutoHeadline(unittest.TestCase):
    def test_never_cuts_mid_word(self):
        h = auto_headline({"officialTitle": "Public Hearing (LDCPAL-2026-6 Innovation Environmental Park Expansion) (Transmittal Hearing) to consider the adoption of an amendment"}, False)
        self.assertTrue(h.endswith("…"))
        self.assertLessEqual(len(h), 111)
        self.assertNotRegex(h, r"[a-z]…$" if h[:-1].endswith(" ") else r"^$")

    def test_two_motions_on_one_item_read_differently(self):
        t = "Consider removal of Commissioner Scott as the liaison to CareerSource Polk and assigning a new liaison."
        a = auto_headline({"officialTitle": t, "motion": "Remove Commissioner Scott as the liaison to CareerSource Polk."}, True)
        b = auto_headline({"officialTitle": t, "motion": "Assign Commissioner Troutman as the new liaison to CareerSource Polk."}, True)
        self.assertNotEqual(a, b)

    def test_drops_consider_and_boilerplate_motion(self):
        self.assertEqual(auto_headline({"officialTitle": "Consider the budget.", "motion": "A motion was made by Commissioner X"}, True), "Budget.")


class Dist(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT / "site" / "region.json").exists() or not (ROOT / "site" / "c").exists():
            raise unittest.SkipTest("site not built")
        cls.region = json.loads((ROOT / "site" / "region.json").read_text())
        cls.out = build_dist()

    def test_every_page_has_its_own_file_title_and_canonical(self):
        for path, c, obj in pages(self.region):
            f = self.out / ("index.html" if path == "/" else path.lstrip("/") + ".html")
            doc = f.read_text()
            self.assertEqual(doc.count("<title>"), 1, path)
            self.assertIn(f'<link rel="canonical" href="https://glassballot.org{path}">', doc)
            self.assertIn('id="app"', doc)
            self.assertNotIn('href="#/', doc, path)

    def test_sitemap_lists_every_page(self):
        n = len(list(pages(self.region)))
        self.assertEqual(len(re.findall("<loc>", (self.out / "sitemap.xml").read_text())), n)

    def test_race_title_names_candidates(self):
        c = self.region["counties"]["pinellas"]
        r = next(x for x in c["races"] if x["id"] == "bcc-d2")
        t, _ = page_meta("/pinellas/r/bcc-d2", c, r, {p["id"]: p for p in c["people"]})
        self.assertIn("Tim Hughes vs. Brian Scott", t)

    def test_unknown_addresses_fall_back_to_the_app(self):
        self.assertEqual((self.out / "_redirects").read_text().strip(), "/*  /app.html  200")
        self.assertIn('noindex', (self.out / "app.html").read_text())


if __name__ == "__main__":
    unittest.main()
