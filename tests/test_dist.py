"""The packaged site: every page has its own address, title and readable summary."""
import json
import re
import unittest
from pathlib import Path

from pipeline.dist import build_dist, page_meta, is_thin, pages
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
            if is_thin(path, c, obj):
                continue
            f = self.out / ("index.html" if path == "/" else path.lstrip("/") + ".html")
            doc = f.read_text()
            self.assertEqual(doc.count("<title>"), 1, path)
            self.assertIn(f'<link rel="canonical" href="https://glassballot.org{path}">', doc)
            self.assertIn('id="app"', doc)
            self.assertNotIn('href="#/', doc, path)

    def test_sitemap_lists_every_page_with_content(self):
        all_ = list(pages(self.region))
        n = sum(not is_thin(*x) for x in all_)
        self.assertEqual(len(re.findall("<loc>", (self.out / "sitemap.xml").read_text())), n)

    def test_empty_pages_are_noindex_and_out_of_the_sitemap(self):
        sm = (self.out / "sitemap.xml").read_text()
        thin = [x for x in pages(self.region) if is_thin(*x)]
        for path, c, obj in thin:
            doc = (self.out / (path.lstrip("/") + ".html")).read_text()
            self.assertIn('<meta name="robots" content="noindex">', doc, path)
            self.assertNotIn('rel="canonical"', doc, path)
            self.assertNotIn(f"<loc>https://glassballot.org{path}</loc>", sm)

    def test_race_title_names_candidates(self):
        c = self.region["counties"]["pinellas"]
        r = next(x for x in c["races"] if x["id"] == "bcc-d2")
        t, _ = page_meta("/pinellas/r/bcc-d2", c, r, {p["id"]: p for p in c["people"]})
        self.assertIn("Tim Hughes vs. Brian Scott", t)

    def test_unknown_addresses_fall_back_to_the_app(self):
        # Cloudflare Pages: a catch-all rewrite would override real files, so unknown addresses get 404.html (the app).
        self.assertFalse((self.out / "_redirects").exists())
        self.assertEqual((self.out / "404.html").read_text(), (self.out / "app.html").read_text())
        self.assertIn('noindex', (self.out / "app.html").read_text())

    def test_cache_control_set_once_per_path(self):
        h = (self.out / "_headers").read_text()
        self.assertEqual(h.count("Cache-Control"), 1)
        self.assertIn("/assets/app-*\n  Cache-Control: public, max-age=31536000, immutable", h)


if __name__ == "__main__":
    unittest.main()
