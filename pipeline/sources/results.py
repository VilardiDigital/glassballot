"""Election night results for county commission and school board races.

Source: each county Supervisor of Elections' results page on enr.electionsfl.org (VR Systems),
found by tools/probe_enr.py and listed in data/enr_ids.json. We record exactly what the page shows:
votes, percentages, precincts reporting, and whether the county calls the results unofficial or official.
We never call a winner ourselves before every precinct is counted.

    python -m pipeline.sources.results            # pull every county with a results page
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENR = "https://enr.electionsfl.org"


def _num(s: str) -> float:
    s = (s or "").replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse(page: str) -> dict:
    """Turn an enr.electionsfl.org Summary page into races."""
    head = " ".join(re.sub(r"<[^>]+>", " ", h) for h in re.findall(r"<h\d[^>]*>[\s\S]{0,200}?</h\d>", page))
    head = re.sub(r"\s+", " ", html.unescape(head))
    status = "official" if re.search(r"\bOFFICIAL RESULTS\b", head) and not re.search(r"UNOFFICIAL", head) else "unofficial"
    m = re.search(r"Last Updated:?\s*([^|<]+?)(?:\s{2}|$)", head)
    races = []
    blocks = re.split(r'<div id="\d+" class="Race row">', page)[1:]
    for b in blocks:
        nm = re.search(r'<label>([^<]+)</label>\s*</label>', b) or re.search(r'class="row RaceName">[\s\S]*?<label>([^<]+)</label>', b)
        if not nm:
            continue
        rep = re.search(r'class="numPrecinctsReported">(\d+)</span>\s*/\s*<span[^>]*class="numPrecinctsParticipating">(\d+)', b)
        graph = b.split('class="row GraphicalResults"', 1)[-1]
        cands = []
        for cm in re.finditer(r'<div class="ChoiceColumn col-xs-4">\s*([^<]+?)\s*</div>(?:(?!ChoiceColumn)[\s\S])*?<div class="ResultsColumn notranslate col-xs-2">([\d.,]+)%</div>\s*<div class="ResultsColumn notranslate col-xs-2"[^>]*>([\d,]+)</div>', graph):
            name = re.sub(r"\s+", " ", html.unescape(cm.group(1))).strip()
            pm = re.match(r"(.*?)\s*\((\w+)\)$", name)
            cands.append({"name": pm.group(1) if pm else name, "party": pm.group(2) if pm else None, "pct": _num(cm.group(2)), "votes": int(_num(cm.group(3)))})
        races.append({"office": html.unescape(nm.group(1)).strip(), "reported": int(rep.group(1)) if rep else None,
                      "precincts": int(rep.group(2)) if rep else None, "candidates": cands})
    return {"status": status, "updated": m.group(1).strip() if m else None, "races": races}


def _key(office: str):
    from ..bootstrap import office_kind, district_of
    kind, _ = office_kind(office, council="city council" in office.lower())
    return (kind, district_of(office)) if kind else None


def _last(n: str) -> str:
    w = re.sub(r'"[^"]*"|\b(Jr|Sr|II|III|IV)\b\.?', " ", n).replace(",", " ").split()
    return w[-1].lower() if w else ""


def merge(seed: dict, county: str) -> dict:
    """Attach results to the county's races when we have them."""
    f = ROOT / "data" / "results" / f"{county}.json"
    if not f.exists():
        return seed
    d = json.loads(f.read_text())
    seed["sources"].setdefault("enr-2026g", {"title": "2026 General Election results", "url": d["url"],
                                            "publisher": f"{seed['county']['name']} Supervisor of Elections", "tier": 1, "accessed": d["pulledAt"][:10]})
    by = {}
    for r in d["races"]:
        k = _key(r["office"])
        if k:
            by.setdefault(k, r)
    people = {p["id"]: p for p in seed["people"]}
    for race in seed["races"]:
        rid = race["id"]
        kind = "sb" if rid.startswith("sb") else "bcc"
        dist = (re.search(r"-d(\d+)$", rid) or [None, None])[1]
        r = by.get((kind, str(int(dist)) if dist else None))
        if not r or not r["candidates"]:
            continue
        total = sum(c["votes"] for c in r["candidates"])
        rows = []
        for c in r["candidates"]:
            pid = next((p for p in race["people"] if people.get(p) and _last(people[p]["name"]) == _last(c["name"])), None)
            rows.append({**c, "person": pid})
        done = r["reported"] is not None and r["precincts"] and r["reported"] >= r["precincts"]
        lead = max(rows, key=lambda c: c["votes"]) if total else None
        race["results"] = {"status": d["status"], "reported": r["reported"], "precincts": r["precincts"], "total": total,
                           "candidates": sorted(rows, key=lambda c: -c["votes"]), "counted": bool(done),
                           "leader": lead["person"] if lead else None, "updated": d.get("updated") or d["pulledAt"], "source": "enr-2026g"}
    return seed


def pull(county: str, code: str, eid: int) -> str:
    from ..refresh import get
    url = f"{ENR}/{code}/{eid}/Summary/"
    page = get(url, as_json=False)
    res = parse(page)
    keep = [r for r in res["races"] if _key(r["office"])]
    out = ROOT / "data" / "results"
    out.mkdir(exist_ok=True)
    (out / f"{county}.json").write_text(json.dumps({"county": county, "url": url, "pulledAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                    "status": res["status"], "updated": res["updated"], "races": keep}, indent=1, ensure_ascii=False))
    votes = sum(c["votes"] for r in keep for c in r["candidates"])
    return f"{county}: {len(keep)} local races, {votes:,} votes counted ({res['status']})"


def main(argv: list[str]):
    ids = json.loads((ROOT / "data" / "enr_ids.json").read_text())
    log = []
    for county, v in ids.items():
        if argv and county not in argv:
            continue
        if v.get("general"):
            try:
                log.append(pull(county, v["code"], v["general"]))
            except Exception as e:
                log.append(f"{county}: results pull failed: {e}")
    print("\n".join(log))


if __name__ == "__main__":
    main(sys.argv[1:])
