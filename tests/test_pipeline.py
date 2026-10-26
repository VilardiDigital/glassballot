"""Run with:  python -m unittest discover -s tests -v   (from the project folder)"""

import json
import unittest
from pathlib import Path

from pipeline.build import build
from pipeline.score import pocket_or_public, money_timing
from pipeline.sources import legistar
from pipeline.verify import label_fact

ROOT = Path(__file__).resolve().parents[1]
SEED = json.loads((ROOT / "data" / "seed_pinellas.json").read_text())
REG = {
    "county": {"tier": 1, "publisher": "County"},
    "clerk": {"tier": 1, "publisher": "Clerk"},
    "news1": {"tier": 4, "publisher": "Paper A"},
    "news2": {"tier": 4, "publisher": "Paper B"},
    "news1b": {"tier": 4, "publisher": "Paper A"},
}


class LabelRules(unittest.TestCase):
    def test_unknown_when_no_claims(self):
        self.assertEqual(label_fact([], REG)["label"], "unknown")

    def test_verified_needs_official_plus_independent(self):
        f = label_fact([{"value": "5-2", "source": "county"}, {"value": "5-2", "source": "news1"}], REG)
        self.assertEqual(f["label"], "verified")

    def test_single_official(self):
        self.assertEqual(label_fact([{"value": "x", "source": "county"}], REG)["label"], "single")

    def test_news_alone_is_unverified_even_if_two_agree(self):
        f = label_fact([{"value": "5-2", "source": "news1"}, {"value": "5-2", "source": "news2"}], REG)
        self.assertEqual(f["label"], "unverified")
        self.assertIn("2 independent", f["note"])

    def test_same_publisher_twice_is_not_independent(self):
        f = label_fact([{"value": "y", "source": "news1"}, {"value": "y", "source": "news1b"}], REG)
        self.assertIn("One non-official", f["note"])

    def test_formatting_differences_are_not_conflicts(self):
        f = label_fact([{"value": "$115,775", "source": "county"}, {"value": "115775", "source": "news1"}], REG)
        self.assertEqual(f["label"], "verified")

    def test_conflict_keeps_every_version_and_marks_official(self):
        f = label_fact([{"value": "2018", "source": "news1"}, {"value": "2019", "source": "county"}], REG)
        self.assertEqual(f["label"], "conflict")
        self.assertEqual(len(f["versions"]), 2)
        self.assertTrue(f["versions"][0]["official"])
        self.assertEqual(f["value"], "2019")

    def test_less_detailed_wording_is_agreement(self):
        f = label_fact([{"value": "Approved", "source": "news1"}, {"value": "Passed unanimously", "source": "county"}], REG)
        self.assertEqual(f["label"], "verified")
        self.assertEqual(f["value"], "Passed unanimously")

    def test_numbers_never_merge_by_prefix(self):
        f = label_fact([{"value": "$11,515", "source": "news1"}, {"value": "$115,775", "source": "county"}], REG)
        self.assertEqual(f["label"], "conflict")

    def test_conflict_without_official_has_no_winner(self):
        f = label_fact([{"value": "a", "source": "news1"}, {"value": "b", "source": "news2"}], REG)
        self.assertIsNone(f["value"])


class Score(unittest.TestCase):
    def test_no_overall_under_minimum_votes(self):
        s = pocket_or_public({"scored_votes": 3})
        self.assertIsNone(s["overall"])
        self.assertIn("3 of 25", s["reason"])

    def test_overall_when_enough_record(self):
        s = pocket_or_public({
            "scored_votes": 40,
            "stake_votes": [{"disclosed": True, "abstained": True}, {"disclosed": False, "abstained": False}],
            "promises": [{"matched": True}, {"matched": False}, {"matched": None}],
            "filings": [{"on_time": True, "complete": True}], "meetings_held": 10, "meetings_attended": 9,
        })
        self.assertEqual(s["parts"]["conflict_handling"], 50.0)
        self.assertEqual(s["parts"]["promise_match"], 50.0)
        self.assertEqual(s["parts"]["openness"], 95.0)
        self.assertEqual(s["overall"], 65)

    def test_money_timing_flags_gifts_near_stake_votes(self):
        contributions = [
            {"donor_id": "dev", "amount": 1000, "date": "2026-03-01"},
            {"donor_id": "dev", "amount": 1000, "date": "2024-01-01"},
            {"donor_id": "nurse", "amount": 2000, "date": "2026-03-01"},
        ]
        self.assertEqual(money_timing(contributions, {"dev": ["2026-04-15"]}), 75.0)


def fake_legistar(tally="5-2", flowers_vote="Aye"):
    votes = [{"VotePersonName": n, "VoteValueName": v} for n, v in [
        ("Dave Eggers", "Aye"), ("Rene Flowers", flowers_vote), ("Chris Latvala", "Aye"),
        ("Kathleen Peters", "Aye"), ("Brian Scott", "Aye"), ("Vince Nowicki", "Nay"), ("Chris Scherer", "Nay")]]
    routes = {
        "bodies": [{"BodyId": 138, "BodyName": "Board of County Commissioners"}],
        "persons": [],
        "events": [{"EventId": 1, "EventDate": "2024-12-17T00:00:00", "EventInSiteURL": "https://pinellas.legistar.com/MeetingDetail.aspx?ID=1"}],
        "events/1/eventitems": [
            {"EventItemId": 11, "EventItemTitle": "Approve Rays stadium bond issuance (tourist development tax)", "EventItemPassedFlag": 1, "EventItemTally": tally, "EventItemActionName": "approved"},
            {"EventItemId": 12, "EventItemTitle": "Consent agenda", "EventItemPassedFlag": 1, "EventItemActionName": "approved"},
        ],
        "eventitems/11/votes": votes,
        "eventitems/12/votes": [{"VotePersonName": "Dave Eggers", "VoteValueName": "Aye"}, {"VotePersonName": "J. Nobody", "VoteValueName": "Aye"}],
    }

    def fetch(url):
        path = url.split("/v1/pinellas/")[1].split("?")[0]
        return routes[path]
    return fetch


class LegistarFlow(unittest.TestCase):
    def setUp(self):
        legistar.RAW_DIR = ROOT / "data" / "raw-test"

    def test_seed_only_rays_vote_is_unverified(self):
        data = build(SEED)
        rays = next(v for v in data["votes"] if v["id"] == "rays-bonds")
        self.assertEqual(rays["result"]["label"], "unverified")

    def test_official_roll_call_upgrades_to_verified(self):
        pull = legistar.pull("pinellas", "Board of County Commissioners", "2024-01-01", fetch=fake_legistar())
        data = build(SEED, pull)
        rays = next(v for v in data["votes"] if v["id"] == "rays-bonds")
        self.assertEqual(rays["result"]["label"], "verified")
        self.assertEqual(rays["roll"]["label"], "verified")
        self.assertTrue(rays["sourceUrl"].startswith("https://pinellas.legistar.com"))

    def test_official_record_disagreeing_with_news_is_a_conflict(self):
        pull = legistar.pull("pinellas", "Board of County Commissioners", "2024-01-01", fetch=fake_legistar(flowers_vote="Nay", tally="4-3"))
        data = build(SEED, pull)
        rays = next(v for v in data["votes"] if v["id"] == "rays-bonds")
        self.assertEqual(rays["roll"]["label"], "conflict")
        self.assertTrue(any(p["field"] == "roll" for p in data["problems"]))

    def test_typed_tally_mismatch_is_logged(self):
        pull = legistar.pull("pinellas", "Board of County Commissioners", "2024-01-01", fetch=fake_legistar(tally="6-1"))
        data = build(SEED, pull)
        self.assertTrue(any(p["field"] == "vote tally" for p in data["problems"]))

    def test_unmatched_names_are_logged_and_extra_items_kept(self):
        pull = legistar.pull("pinellas", "Board of County Commissioners", "2024-01-01", fetch=fake_legistar())
        data = build(SEED, pull)
        self.assertTrue(any(p["field"] == "voter names" for p in data["problems"]))
        extra = [v for v in data["votes"] if v["id"] == "lg-12"]
        self.assertEqual(len(extra), 1)
        self.assertIsNone(extra[0]["inShort"])


class SeedData(unittest.TestCase):
    def test_every_claim_cites_a_known_source(self):
        ids = set(SEED["sources"])
        def walk(o):
            if isinstance(o, dict):
                if "source" in o:
                    self.assertIn(o["source"], ids)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(SEED)

    def test_official_record_settles_old_disagreement(self):
        # Ballot Brief said 2018, Ballotpedia said 2019; the county's own page says 2018.
        data = build(SEED)
        peters = next(p for p in data["people"] if p["id"] == "peters")
        self.assertEqual(peters["facts"]["inOfficeSince"]["value"], "2018")
        self.assertIn(peters["facts"]["inOfficeSince"]["label"], ("verified", "single"))
        self.assertTrue(peters["facts"]["inOfficeSince"]["otherReports"])

    def test_no_overall_scores_on_thin_record(self):
        data = build(SEED)
        self.assertTrue(all(p["score"]["overall"] is None for p in data["people"]))


if __name__ == "__main__":
    unittest.main()


class SummaryMerge(unittest.TestCase):
    def setUp(self):
        from pipeline.sources.legistar_summary import merge
        self.summary = json.loads((ROOT / "data" / "legistar_pinellas_summary.json").read_text())
        self.data = build(merge(SEED, self.summary))

    def test_rays_upgrades_to_verified_with_official_record(self):
        rays = next(v for v in self.data["votes"] if v["id"] == "rays-bonds")
        self.assertEqual(rays["result"]["label"], "verified")
        self.assertEqual(rays["roll"]["label"], "verified")

    def test_every_split_vote_loaded_and_official(self):
        split = [v for v in self.data["votes"] if v.get("split")]
        self.assertEqual(len(split), len(self.summary["splitVotes"]))
        self.assertTrue(all(v["roll"]["label"] == "single" for v in split))

    def test_roll_counts_match_result_text(self):
        import re
        for v in self.data["votes"]:
            m = re.search(r"(\d+) to (\d+)", v["result"].get("value") or "")
            r = v["roll"].get("value")
            if m and r and v["result"]["label"] != "conflict":
                self.assertEqual((int(m.group(1)), int(m.group(2))), (len(r["yes"]), len(r["no"])), v["id"])

    def test_attendance_scored_but_no_overall(self):
        n = next(p for p in self.data["people"] if p["id"] == "nowicki")
        self.assertEqual(n["score"]["parts"]["openness"], 100.0)
        self.assertIsNone(n["score"]["overall"])

    def test_vote_dates_from_record(self):
        bh = next(v for v in self.data["votes"] if v["id"] == "behavioral-urgent-care")
        self.assertEqual(bh["date"], "2026-09-24")


class PreferOfficial(unittest.TestCase):
    def test_official_profile_fact_stands_with_other_reports_listed(self):
        reg = {"soe": {"tier": 1, "publisher": "SOE"}, "news": {"tier": 4, "publisher": "News"}}
        from pipeline.verify import label_fact
        f = label_fact([{"value": "Elected Nov 2020", "source": "soe"}, {"value": "Nov 17, 2020", "source": "news"}], reg, prefer_official=True)
        self.assertEqual(f["label"], "single")
        self.assertEqual(f["value"], "Elected Nov 2020")
        self.assertEqual(f["otherReports"][0]["value"], "Nov 17, 2020")

    def test_two_official_records_disagreeing_is_still_a_conflict(self):
        reg = {"a": {"tier": 1, "publisher": "County"}, "b": {"tier": 1, "publisher": "SOE"}}
        from pipeline.verify import label_fact
        f = label_fact([{"value": "2022", "source": "a"}, {"value": "2024", "source": "b"}], reg, prefer_official=True)
        self.assertEqual(f["label"], "conflict")


class VoterFocusParse(unittest.TestCase):
    def test_parses_office_groups(self):
        from pipeline import refresh
        page = ('<select name="el"><option value=\'35\' selected>2026 Candidate Election Cycle (11/3/2026)</option></select>'
                '<div class="col-xs-12 officegroup"> <div class="col-xs-12 officename">Office: County Commission, Dist 2</div>'
                '<div class="detailrow"> <a class="rowlink" href="/CampaignFinance/candidate_pr.php?op=cv&e=32&c=hernando&ca=628&rellevel=4&committee=N">'
                '<div> Kathryn Birren (REP) </div><div>status (Active-Unopposed)</div><div>Contributions monetary $97,425.00</div><div>In-Kind in-kind $944.76</div></a></div></div>'
                '<div class="col-xs-12 officegroup"> <div class="col-xs-12 officename">Office: Sheriff</div><a href="x?ca=1">Y (REP) status (Active) Contributions monetary $1.00 In-Kind in-kind $0.00</a></div>')
        refresh.get = lambda url, as_json=True, tries=4: page
        rows = refresh.refresh_voterfocus("hernando", None, "2026-10-26")
        self.assertEqual(rows, ["hernando|35|County Commission, Dist 2|Kathryn Birren|REP|Active-Unopposed|97,425.00|944.76|628"])
