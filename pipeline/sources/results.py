"""Election night results for county commission and school board races.

Source: each county Supervisor of Elections' results page. Most counties use enr.electionsfl.org
(VR Systems), found by tools/probe_enr.py. A few (Pinellas) use Clarity Elections, which publishes a
summary file (json/sum.json); tools/probe_clarity.py finds those. Both are listed in data/enr_ids.json. We record exactly what the page shows:
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
        for cm in re.finditer(r'<div class="ChoiceColumn col-xs-4">\s*([^<]+?)\s*</div>(?:(?!ChoiceColumn)[\s\S])*?<div class="ResultsColumn notranslate col-xs-2">([\d.,]+)(?:%|&#37;)</div>\s*<div class="ResultsColumn notranslate col-xs-2"[^>]*>([\d,]+)</div>', graph):
            name = re.sub(r"\s+", " ", html.unescape(cm.group(1))).strip()
            pm = re.match(r"(.*?)\s*\((\w+)\)$", name)
            cands.append({"name": pm.group(1) if pm else name, "party": pm.group(2) if pm else None, "pct": _num(cm.group(2)), "votes": int(_num(cm.group(3)))})
        if not cands:
            # Nov 2026 layout: the totals live in the "DetailResults" table (one row per choice).
            table = (re.search(r'<table class="DetailResults"[\s\S]*?</table>', b) or [""])[0]
            for row in re.findall(r"<tr>\s*<td class=\"ChoiceColumn\">([\s\S]*?)</tr>", table):
                name = re.sub(r"\s+", " ", html.unescape(re.sub(r"<div[\s\S]*", "", row))).strip()
                tot = re.search(r'class="DetailResultsColumn notranslate TotalVotes">([\d,]+)<', row)
                pct = re.findall(r'class="DetailResultsColumn notranslate">([\d.]+)%<', row)
                if not name or not tot:
                    continue
                pm = re.match(r"(.*?)\s*\((\w+)\)$", name)
                party = pm.group(2) if pm else None
                cands.append({"name": pm.group(1) if pm else name, "party": None if party in ("NON", "NPA") and "School Board" in b[:3000] else party,
                              "pct": _num(pct[-1]) if pct else 0.0, "votes": int(_num(tot.group(1)))})
        races.append({"office": html.unescape(nm.group(1)).strip(), "reported": int(rep.group(1)) if rep else None,
                      "precincts": int(rep.group(2)) if rep else None, "candidates": cands})
    return {"status": status, "updated": m.group(1).strip() if m else None, "races": races}


def parse_clarity(summary: dict) -> dict:
    """Turn a Clarity Elections json/sum.json file into races. Clarity doesn't mark results official,
    so these stay 'unofficial' until the county certifies and we check the certified report."""
    races = []
    for c in summary.get("Contests", []):
        names, votes, pcts, parties = c.get("CH") or [], c.get("V") or [], c.get("PCT") or [], c.get("P") or []
        cands = []
        for i, n in enumerate(names):
            party = parties[i] if i < len(parties) else None
            name = re.sub(r"\s+", " ", n).strip()
            if party and name.upper().startswith(party.upper() + " "):
                name = name[len(party) + 1:].strip()  # Clarity puts the party in front of the name: "REP Brian Scott"
            cands.append({"name": name, "party": None if party in (None, "", "NON", "NPA") else party,
                          "pct": round(float(pcts[i]), 2) if i < len(pcts) and pcts[i] is not None else 0.0, "votes": int(votes[i]) if i < len(votes) else 0})
        races.append({"office": re.sub(r"\s+", " ", c.get("C", "")).strip(), "reported": c.get("PR"), "precincts": c.get("TP"), "candidates": cands})
    return {"status": "unofficial", "updated": None, "races": races}


NOT_LOCAL = re.compile(r"\b(city|town|village|referendum|millage|surtax|sales tax|ad valorem|amendment|amdt|resolution|charter|funding|expenses|"
                       r"agriculture|single member|question|retention|ballot|residency)\b|amdt", re.I)


def _key(office: str):
    """(kind, district) for a county commission or school board seat; None for anything else.
    Strict on purpose: a city council or a school tax question must never land on a county race."""
    o = re.sub(r"\s+", " ", office).strip()
    o = re.sub(r"\s*-\s*(single member|at large|at-large|countywide)\s*$", "", o, flags=re.I)  # "District 6 - Single Member" is a seat, not a question
    if NOT_LOCAL.search(o):
        return None
    if re.search(r"\b(board of county commissioners|county commissioner|county commission|county council)\b", o, re.I):
        kind = "bcc"
    elif re.search(r"\bschool board\b", o, re.I):
        kind = "sb"
    else:
        return None
    from ..bootstrap import district_of
    return (kind, district_of(o))


def _last(n: str) -> str:
    w = re.sub(r'"[^"]*"|\b(Jr|Sr|II|III|IV)\b\.?', " ", n).replace(",", " ").split()
    return w[-1].lower() if w else ""


GROUPS = [
    ("statewide", "Statewide", r"^(united states senator|governor|attorney general|chief financial officer|commissioner of agriculture)\b"),
    ("amendment", "Statewide amendments", r"constitutional amendment|^no\.? ?\d+ constitutional|^amendment"),
    ("congress", "U.S. House", r"representative in congress"),
    ("legislature", "State Legislature", r"state senator|state representative"),
    ("courts", "Judges and court retention", r"justice|judge|court of appeal|circuit|county court|retain"),
    ("county", "County offices", r"county commission|board of county|county council|sheriff|clerk|property appraiser|tax collector|supervisor of elections|county mayor"),
    ("schools", "School board", r"school board|superintendent"),
    ("measure", "Local ballot questions", r"referendum|question|millage|charter|ordinance|bond|straw|ad valorem|sales tax|surtax|exemption|shall"),
    ("district", "Special districts", r"\bcdd\b|community development|mosquito|fire (control|rescue|district)|hospital|drainage|water control|improvement district|port authority|soil and water|library district|recreation district"),
    ("city", "City and town", r"city|town|village|mayor|council|commissioner|alderman"),
    ("district", "Special districts", r"cdd|district|fire|hospital|drainage|water|seat|supervisor|trustee"),
]


def group_of(office: str) -> str:
    o = office.lower()
    for k, _, rx in GROUPS:
        if re.search(rx, o):
            return k
    return "other"


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
    seed["county"]["ballotResults"] = {"status": d["status"], "updated": d.get("updated") or d["pulledAt"], "url": d["url"],
        "races": [{"office": r["office"], "group": group_of(r["office"]), "reported": r["reported"], "precincts": r["precincts"],
                   "total": sum(c["votes"] for c in r["candidates"]), "candidates": sorted(r["candidates"], key=lambda c: -c["votes"])}
                  for r in d.get("all", []) if r["candidates"]]}
    people = {p["id"]: p for p in seed["people"]}
    for race in seed["races"]:
        rid = race["id"]
        kind = "sb" if rid.startswith("sb") else "bcc"
        dist = (re.search(r"-d(\d+)$", rid) or [None, None])[1]
        r = by.get((kind, str(int(dist)) if dist else None))
        if not r or not r["candidates"]:
            if race.get("onNovBallot") is not False and d.get("all"):
                race["notInResults"] = {"url": d["url"], "source": "enr-2026g"}  # the county's Nov 3 results don't list this seat
            continue
        total = sum(c["votes"] for c in r["candidates"])
        if not total:
            continue  # the county has posted the race but no votes yet
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


def pull(county: str, code: str, eid: int, vendor: str = "vr", base: str | None = None, certified: bool = False) -> str:
    from ..refresh import get
    if vendor == "clarity":
        from ..refresh import BROWSERISH
        hdr = {**BROWSERISH, "Referer": f"{base}/{eid}/"}
        ver = get(f"{base}/{eid}/current_ver.txt", as_json=False, tries=6, headers=hdr).strip()
        if not ver.isdigit():
            raise ValueError(f"no current version number from {base}/{eid}/current_ver.txt: {ver[:60]!r}")
        res = parse_clarity(get(f"{base}/{eid}/{ver}/json/sum.json", tries=6, headers=hdr))
        url = f"{base}/{eid}/"
    else:
        url = f"{ENR}/{code}/{eid}/Summary/"
        res = parse(get(url, as_json=False))
    if certified:
        res["status"] = "official"  # set by hand in data/enr_ids.json once the canvassing board certifies (Clarity pages never say so)
    keep = [r for r in res["races"] if _key(r["office"])]
    out = ROOT / "data" / "results"
    out.mkdir(exist_ok=True)
    (out / f"{county}.json").write_text(json.dumps({"county": county, "url": url, "pulledAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                    "status": res["status"], "updated": res["updated"], "races": keep,
                                                    "all": [r for r in res["races"] if r["candidates"]]}, indent=1, ensure_ascii=False))
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
                log.append(pull(county, v.get("code"), v["general"], v.get("vendor", "vr"), v.get("base"), bool(v.get("certified"))))
            except Exception as e:
                log.append(f"{county}: results pull failed: {e}")
    print("\n".join(log))


if __name__ == "__main__":
    main(sys.argv[1:])
