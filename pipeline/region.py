"""Build every county and bake one statewide site.

    python -m pipeline.region --accessed 2026-10-26

Each county is built from its seed plus whatever official pulls exist for it
(data/legistar_<county>_summary.json, data/money_<county>.json). Counties whose
seed file doesn't exist yet are skipped, so the site never shows an empty county.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .build import build
from .sources.legistar_summary import merge as merge_summary
from .sources.money import merge as merge_money
from .sources.filings import merge as merge_filings
from .sources.dig import merge as merge_dig
from .sources.impact import merge as merge_impact
from .sources.funding import merge as merge_funding
from .sources.results import merge as merge_results

ROOT = Path(__file__).resolve().parents[1]
_REG = json.loads((ROOT / "data" / "counties.json").read_text())["counties"]
ORDER = sorted((k for k, c in _REG.items() if c.get("live")), key=lambda k: _REG[k].get("order", 999))


def build_county(cid: str, accessed: str | None) -> dict | None:
    seed_p = ROOT / "data" / f"seed_{cid}.json"
    if not seed_p.exists():
        return None
    seed = json.loads(seed_p.read_text())
    summ = ROOT / "data" / f"legistar_{cid}_summary.json"
    money = ROOT / "data" / f"money_{cid}.json"
    if summ.exists():
        seed = merge_summary(seed, json.loads(summ.read_text()))
    if money.exists():
        seed = merge_money(seed, json.loads(money.read_text()))
    seed = merge_filings(seed, cid)
    seed = merge_dig(seed, cid)
    seed = merge_impact(seed, cid)
    seed = merge_funding(seed, cid)
    seed = merge_results(seed, cid)
    d = build(seed, None, accessed)
    # "We still need to open this page" is our work queue, not a problem with the public record.
    todo = [x for x in d["problems"] if x.get("kind") == "needs-browser-fetch"]
    d["problems"] = [x for x in d["problems"] if x.get("kind") != "needs-browser-fetch"]
    (ROOT / "data" / f"todo_{cid}.json").write_text(json.dumps(todo, indent=1, ensure_ascii=False))
    return d


def build_region(accessed: str | None = None) -> dict:
    counties = {}
    for cid in ORDER:
        d = build_county(cid, accessed)
        if d:
            counties[cid] = d
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "region": {"name": "Florida", "state": "FL", "electionDate": "2026-11-03", "updated": accessed or today},
        "order": [c for c in ORDER if c in counties],
        "counties": counties,
        "changes": [json.loads(f.read_text()) for f in sorted((ROOT / "data" / "changes").glob("*.json"), reverse=True)[:30]] if (ROOT / "data" / "changes").exists() else [],
        "corrections": json.loads((ROOT / "data" / "corrections.json").read_text()),
        "zips": json.loads((ROOT / "site" / "assets" / "zips_fl.json").read_text()),  # every Florida ZIP to its county (Census 2020)
        "howToVote": json.loads((ROOT / "data" / "howtovote.json").read_text()) if (ROOT / "data" / "howtovote.json").exists() else {"statewide": [], "counties": {}, "jobs": {}},
        "closeRace": {"headline": "Local races can be very close.", "detail": "In Hernando County's Aug 18 primary, the top two School Board District 5 candidates finished 7 votes apart: 13,724 to 13,717.", "url": "https://www.hernandovotes.gov/DocumentCenter/View/798"},
        "map": json.loads((ROOT / "site" / "assets" / "fl.json").read_text()),
    }


def _stub(k: str, c: dict) -> dict:
    """What the front page needs about a county before you open it. The full county loads on demand."""
    n = c["county"]["name"].replace(" County", "")
    idx = [[f"#/{k}/p/{p['id']}", p["name"], f"{p.get('office', '')}{', District ' + str(p['district']) if p.get('district') else ''} · {n}"] for p in c["people"]]
    idx += [[f"#/{k}/v/{v['id']}", v["headline"], n] for v in c["votes"]]
    idx += [[f"#/{k}/r/{r['id']}", r["title"], f"{n} County ballot"] for r in c["races"]]
    return {"stub": True, "county": c["county"], "labelCounts": c.get("labelCounts", {}), "nProblems": len(c.get("problems", [])),
            "nRaces": sum(1 for r in c["races"] if r.get("onNovBallot") is not False), "nSources": len(c.get("sources", {})), "index": idx}


def bake(data: dict) -> Path:
    tpl = (ROOT / "site" / "template.html").read_text()
    # Each county is its own file (site/c/<county>.json); the page itself carries only a small summary of each.
    cdir = ROOT / "site" / "c"
    cdir.mkdir(exist_ok=True)
    for k, c in data["counties"].items():
        (cdir / f"{k}.json").write_text(json.dumps(c, ensure_ascii=False, separators=(",", ":")))
    light = {**data, "counties": {k: _stub(k, c) for k, c in data["counties"].items()}}
    blob = json.dumps(light, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    out = ROOT / "site" / "glassballot.html"
    out.write_text(tpl.replace("/*__DATA__*/null", blob))
    (ROOT / "site" / "region.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accessed", default=None)
    a = ap.parse_args()
    data = build_region(a.accessed)
    for k in data["order"]:
        c = data["counties"][k]
        print(f"{k}: {len(c['people'])} people, {len(c['races'])} races, {len(c['votes'])} votes, labels {c['labelCounts']}")
    print("Site:", bake(data))


if __name__ == "__main__":
    main()
