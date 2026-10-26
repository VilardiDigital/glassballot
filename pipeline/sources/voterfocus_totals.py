"""Official campaign totals from each Supervisor of Elections' VoterFocus summary page.

Input: data/voterfocus_totals_<date>.txt, one candidate per line:
county|election id|office|name|party code|status|monetary|in-kind|account id
Adds tier 1 "raised" claims (and party, for partisan seats) to the county seeds.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARTY = {"REP": "Republican", "DEM": "Democrat", "NPA": None, "NON": None, "WRI": None}


def apply(path: Path, asof: str):
    rows = [l.split("|") for l in path.read_text().splitlines() if l.strip()]
    by = {}
    for county, el, office, name, party, status, mon, ink, ca in rows:
        by.setdefault(county, []).append((el, office, name, party, status, mon, ink, ca))
    for county, items in by.items():
        sp = ROOT / "data" / f"seed_{county}.json"
        d = json.loads(sp.read_text())
        sid = f"soe-cf-{county}"
        d["sources"][sid] = {"title": f"{county.title()} Supervisor of Elections campaign finance reports, 2026 cycle",
                             "url": f"https://www.voterfocus.com/CampaignFinance/candidate_pr.php?c={county}&el={items[0][0]}",
                             "publisher": f"{county.title()} County Supervisor of Elections", "tier": 1, "accessed": asof}
        d["county"]["financeUrl"] = d["sources"][sid]["url"]
        hit = 0
        for el, office, name, party, status, mon, ink, ca in items:
            last = name.replace(" Jr.", "").split()[-1].lower()
            first = name.split()[0].lower()
            cands = [p for p in d["people"] if p["name"].lower().split()[-1].strip(".,") == last or last in p["name"].lower()]
            if len(cands) > 1:
                cands = [p for p in cands if p["name"].lower().startswith(first)] or cands
            if len(cands) != 1:
                print("  no match", county, name); continue
            p = cands[0]; hit += 1
            cl = p.setdefault("claims", {})
            from datetime import date
            y, mth, dd = map(int, asof.split("-"))
            nice = date(y, mth, dd).strftime("%b %-d, %Y")
            val = f"${mon.removesuffix('.00')} in contributions" + (f", plus ${ink.removesuffix('.00')} in-kind" if ink not in ("0.00", "0") else "") + f" (as of {nice})"
            cl["raised"] = [c for c in cl.get("raised", []) if c["source"] != sid] + [{"value": val, "source": sid}]
            if PARTY.get(party) and not p.get("nonpartisan"):
                cl["party"] = [c for c in cl.get("party", []) if c["source"] != sid] + [{"value": PARTY[party], "source": sid}]
            p.setdefault("finance", {})["voterfocusId"] = ca
            p["finance"]["status"] = status
        sp.write_text(json.dumps(d, indent=1, ensure_ascii=False))
        print(county, hit, "of", len(items), "matched")


if __name__ == "__main__":
    apply(Path(sys.argv[1]), sys.argv[2])
