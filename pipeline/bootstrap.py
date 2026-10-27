"""Build a first version of a county from official records alone.

    python -m pipeline.bootstrap orange seminole     # writes data/seed_<county>.json

For a county marked "auto" in data/counties.json, this makes:
  - races and candidates, from the Supervisor of Elections' campaign finance site (VoterFocus)
  - current county commissioners, from the county's meeting system when it has a public API (Legistar)
Plain-English summaries, track records and fact checks come later, from people. Until then the
site labels the county as an automatic first version.

Needs network access, so it runs on GitHub Actions, not in the editing container.
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VF = "https://www.voterfocus.com/CampaignFinance/candidate_pr.php"
TOPICS = [
    {"id": "growth", "name": "Growth, land use and housing", "blurb": "Rezonings, land use changes and big new communities."},
    {"id": "taxes", "name": "Taxes and the budget", "blurb": "Property tax rates, fees and how the county spends money."},
    {"id": "roads", "name": "Roads and transportation", "blurb": "Road projects, transit and traffic."},
    {"id": "water", "name": "Water, storms and environment", "blurb": "Flooding, stormwater, beaches and the environment."},
    {"id": "safety", "name": "Public safety", "blurb": "Sheriff, fire rescue and emergency services."},
    {"id": "other", "name": "Other decisions", "blurb": "Everything else the commission voted on."},
]


def get(url: str):
    from .refresh import get as _get
    return _get(url, as_json=False)


def slug(name: str, taken: set) -> str:
    words = re.sub(r"[^A-Za-z \-]", "", name.replace('"', " ")).lower().split()
    words = [w for w in words if w not in ("jr", "sr", "ii", "iii", "iv")]
    base = words[-1].replace("-", "") if words else "person"
    s = base if base not in taken else (words[0] + base if words else base)
    i = 2
    while s in taken:
        s, i = f"{base}{i}", i + 1
    taken.add(s)
    return s


NOT_COUNTY = r"\b(city|town|village|municipal|soil|water|hospital|charter|port|airport|fire|mosquito|drainage|library|community development|recreation|beach|park)\b"


def office_kind(office: str, council: bool = False):
    o = office.lower()
    if re.search(NOT_COUNTY, o) and not (council and "city council" in o):
        return None, None
    if "school" in o:
        return "sb", "School Board"
    if re.search(r"county commission|board of county|commissioner|\bbcc\b", o) or (council and "city council" in o):
        return "bcc", "City Council" if council else "County Commission"
    return None, None


def district_of(office: str):
    m = re.search(r"(?:dist(?:rict)?\.?|seat|group)\s*(\d+)", office, re.I)
    if m:
        return m.group(1)
    if re.search(r"at[- ]large", office, re.I):
        return None
    return None


def voterfocus_races(county: str, slug_: str, el: int, council: bool = False):
    page = get(f"{VF}?c={slug_}&el={el}")
    races = []
    for g in re.split(r'class="col-xs-12 officegroup"', page)[1:]:
        om = re.search(r'officename">\s*Office:\s*(.*?)</div>', g, re.S)
        office = re.sub(r"\s+", " ", html.unescape(om.group(1))).strip() if om else ""
        kind, label = office_kind(office, council)
        if not kind:
            continue
        cands = []
        for a in re.finditer(r'href="[^"]*ca=(\d+)[^"]*">(.*?)</a>', g, re.S):
            text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", a.group(2)))).strip()
            m = re.match(r"(.*?)(?: \((\w+)\))? status \((.*?)\)", text)
            if not m:
                continue
            status = m.group(3).strip()
            if re.search(r"did not qualify|withdrawn|now files with state", status, re.I):
                continue
            cands.append({"name": m.group(1).strip(), "party": m.group(2), "status": status, "ca": a.group(1)})
        if cands:
            races.append({"office": office, "kind": kind, "label": label, "district": district_of(office), "candidates": cands})
    return races


def legistar_members(client: str, body_id: int):
    """Current members of the commission, from Legistar office records."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    q = urllib.parse.quote(f"OfficeRecordBodyId eq {body_id} and OfficeRecordEndDate ge datetime'{today}' and OfficeRecordStartDate le datetime'{today}'")
    try:
        recs = json.loads(get(f"https://webapi.legistar.com/v1/{client}/officerecords?$filter={q}"))
    except Exception:
        return []
    out = []
    for r in recs:
        title = r.get("OfficeRecordTitle") or ""
        if re.search(r"clerk|attorney|administrator|manager|secretary|staff", title, re.I):
            continue
        out.append({"name": (r.get("OfficeRecordFullName") or "").strip(), "title": title, "start": (r.get("OfficeRecordStartDate") or "")[:10]})
    return [m for m in out if m["name"]]


PARTY = {"REP": "Republican", "DEM": "Democrat", "NPA": "No party affiliation", "LPF": "Libertarian", "WRI": "Write-in", "GRE": "Green", "IND": "Independent"}


def build(county: str, cfg: dict) -> dict:
    fin = cfg["finance"]
    el, slug_ = fin["cycle"], fin.get("slug", county)
    name = cfg["name"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    seed = {"county": {"id": county, "name": name, "state": "FL", "body": "Board of County Commissioners", "electionDate": "2026-11-03",
                       "auto": True, "financeUrl": f"{VF}?c={slug_}&el={el}"},
            "sources": {"soe-vf": {"title": f"{name} Supervisor of Elections: 2026 candidates and campaign reports", "url": f"{VF}?c={slug_}&el={el}",
                                   "publisher": f"{name} Supervisor of Elections", "tier": 1, "accessed": now}},
            "people": [], "races": [], "votes": [], "topics": TOPICS, "manualProblems": []}
    taken: set = set()
    people: dict = {}

    def person(nm: str) -> dict:
        key = re.sub(r"[^a-z]", "", nm.lower().replace(" jr", ""))
        if key not in people:
            people[key] = {"id": slug(nm, taken), "name": nm, "claims": {}}
            seed["people"].append(people[key])
        return people[key]

    # Current commissioners, when the meeting system lists them.
    m = cfg.get("meetings", {})
    if m.get("vendor") == "legistar" and m.get("bodies"):
        seed["sources"]["legistar"] = {"title": f"{name} Board of County Commissioners meeting records (Legistar)",
                                       "url": f"https://{m['client']}.legistar.com/Calendar.aspx", "publisher": f"{name} Board of County Commissioners", "tier": 1, "accessed": now}
        for mem in legistar_members(m["client"], m["bodies"][0]):
            p = person(mem["name"])
            p.update({"office": "County Commissioner", "status": "incumbent"})
            dm = re.search(r"district\s*(\d+)", mem["title"], re.I)
            if dm:
                p["district"] = dm.group(1)
            if mem["start"]:
                p["claims"]["inOfficeSince"] = [{"value": mem["start"][:4], "source": "legistar"}]
            if re.search(r"chair|vice", mem["title"], re.I):
                p["claims"]["leadership"] = [{"value": mem["title"], "source": "legistar"}]

    for r in voterfocus_races(county, slug_, el, council=county == "duval"):
        rid = f"{r['kind']}-d{r['district']}" if r["district"] else f"{r['kind']}-{re.sub(r'[^a-z0-9]+', '-', r['office'].lower()).strip('-')[:30]}"
        live = [c for c in r["candidates"] if re.search(r"qualified|runoff|write-in", c["status"], re.I) and not re.search(r"defeated", c["status"], re.I)]
        decided = [c for c in r["candidates"] if re.search(r"elected|unopposed", c["status"], re.I)]
        on_ballot = len(live) >= 2 or any(re.search(r"runoff", c["status"], re.I) for c in live)
        race = {"who": "We haven't confirmed which voters get this race. Your sample ballot shows whether it's on yours.", "id": rid, "title": f"{r['label']}{', District ' + r['district'] if r['district'] else ''}", "office": r["office"], "people": [],
                "sources": ["soe-vf"], "onNovBallot": bool(on_ballot)}
        if not on_ballot and decided:
            race["decided"] = f"{decided[0]['name']} ({decided[0]['status'].split('-')[-1].strip().lower()})"
        for c in r["candidates"]:
            if re.search(r"defeated", c["status"], re.I) and on_ballot:
                continue
            p = person(c["name"])
            p.setdefault("office", f"Candidate, {r['label']}")
            p.setdefault("status", "open")
            if r["district"]:
                p.setdefault("district", r["district"])
            p["race"] = rid
            p["finance"] = {"voterfocusId": c["ca"], "status": c["status"]}
            if r["kind"] == "sb" or not c["party"] or c["party"] in ("NON", "NP", "NPA") and r["kind"] == "sb":
                p["nonpartisan"] = r["kind"] == "sb"
            if c["party"] and r["kind"] != "sb":
                p["claims"]["party"] = [{"value": PARTY.get(c["party"], c["party"]), "source": "soe-vf"}]
            race["people"].append(p["id"])
        seed["races"].append(race)
    return seed


def run(k: str, cfg: dict) -> str:
    out = ROOT / "data" / f"seed_{k}.json"
    if out.exists() and not json.loads(out.read_text()).get("county", {}).get("auto"):
        return f"{k}: has a reviewed seed; not overwriting"
    seed = build(k, cfg)
    if not seed["races"]:
        return f"{k}: no races found; kept the last version"
    out.write_text(json.dumps(seed, indent=1, ensure_ascii=False))
    return f"{k}: {len(seed['people'])} people, {len(seed['races'])} races, {sum(1 for p in seed['people'] if p.get('status') == 'incumbent')} commissioners (automatic)"


def main(names: list[str]):
    reg = json.loads((ROOT / "data" / "counties.json").read_text())["counties"]
    for k in names or [k for k, c in reg.items() if c.get("auto")]:
        print(run(k, reg[k]))


if __name__ == "__main__":
    main(sys.argv[1:])
