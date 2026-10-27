"""Who pays for each campaign, grouped so a voter can read it.

Input: data/contrib/<county>.json, the itemized contributions every candidate files with the
county Supervisor of Elections (VoterFocus "Export All"), pulled nightly by pipeline.refresh.

We group each contribution by:
  - kind of giver: a person, a business, a political committee (PAC), a political party, the candidate
  - industry: from the business name and the occupation the giver reported

The grouping is ours, made by matching words (for example "Realty" or "Paving"), so the site says so
and every group can be opened to see the donors in it. Private individuals are never named; we show
their reported occupation only. Businesses, committees and parties are named, since they are not
private people and their gifts are the point.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ID = "soe-itemized"

# Industry groups, checked in order. Each is (id, label, words matched in the name or occupation).
SECTORS = [
    ("realestate", "Real estate and land development", r"real ?estate|realt|develop|land (?:co|llc|dev|serv|sale)|\bland\b|home ?build|\bhomes?\b|propert|communit|apartment|villas?\b|\bacres\b|title (?:co|agen)|mortgage|landlord|\bholdco\b|\bequities\b"),
    ("construction", "Construction and engineering", r"construct|contract|paving|asphalt|concrete|cement|roof|plumb|electric|hvac|\bac\b|engineer|survey|excavat|drywall|material|dredg|marine (?:serv|contr)|dock|civil|site ?work|builder|lumber|pipe|floors|granite|masonry|demoli|infrastructure|architect"),
    ("law", "Lawyers and lobbyists", r"attorney|lawyer|\blaw\b|legal|lobby|government(?:al)? (?:relations|consult|affairs)|govt\.? relations|public affairs|political consult|strateg|p\.a\.$"),
    ("health", "Health care", r"physician|doctor|\bmd\b|nurse|dental|dentist|dentistry|pharm|medical|hospital|chiropract|therap|urolog|health|clinic|surgeon|podiatr|osteopath"),
    ("finance", "Banking, insurance and investing", r"insur|\bbank|financ|\bcpa\b|accountant|invest|capital|wealth|surety|\bfund\b|asset|equity|family office"),
    ("towing", "Towing, auto and transportation", r"\btow|recovery|auto|dealer|\brv\b|bus lines|transport|logistic|aviation|airport|jet|trucking|leasing"),
    ("hospitality", "Restaurants, hotels and entertainment", r"restaur|hospitality|hotel|\binn\b|grill|\bbar\b|bowl|lanes|entertain|seafood|catering|food|menus|marina"),
    ("waste", "Waste, utilities and energy", r"waste|utilit|water|energy|\bteco\b|duke|\boil\b|gas\b|grease|solar|power"),
    ("agriculture", "Farming and agriculture", r"farm|agricult|ranch|citrus|nursery|cattle"),
    ("education", "Schools and education", r"teacher|educat|school|professor|principal|tutor|universit|college"),
    ("public", "Government and public safety jobs", r"firefight|fire ?fighter|battalion|police|sheriff|law enforcement|deputy|county|city of|government|public servant|commissioner|appraiser|code compliance|budget director"),
]
NO_JOB = r"retire|homemaker|not employed|unemployed|student|none"


def sector(text: str) -> str | None:
    t = (text or "").lower()
    for sid, _, rx in SECTORS:
        if re.search(rx, t):
            return sid
    return None


# Political committees. Names alone often don't say who is behind a committee, so we only describe
# the ones whose names plainly say it; the rest are listed as "purpose not stated in its name".
COMMITTEE_KINDS = [
    ("union", "Labor union committee", r"\bunion\b|local \d|\biuoe\b|\bibew\b|teamsters|\bcta\b|education association|labor|firefighters|benevolent|\bpba\b|iron workers|pipefitters|\bafl|\bseiu\b|\bpcta\b|teachers|\bflame\b"),
    ("industry", "Industry or trade group committee", r"realtor|home builders|apartment|\bftba\b|transportation builders|\babc\b|builders and contractors|podiatr|osteopath|medical|hospital|physician|\bwgi\b|infrastructure|shumaker|chamber|\bbar\b|prescription|nurses|dental|engineers|bankers|auto dealers|farm bureau"),
    ("politician", "Another politician's committee", r"^friends of|for florida$|^committee to elect|\bfor (?:senate|house|sheriff|commission|congress)\b"),
]


def committee_kind(name: str) -> str:
    n = (name or "").lower()
    for kid, _, rx in COMMITTEE_KINDS:
        if re.search(rx, n):
            return kid
    return "other"


KIND_LABEL = {k: l for k, l, _ in COMMITTEE_KINDS} | {"other": "Political committee (its name doesn't say who funds it)"}
SECTOR_LABEL = {s: l for s, l, _ in SECTORS} | {"other-business": "Other businesses", "other-job": "Other jobs", "nojob": "Retired or not working", "unstated": "Job not reported"}


ENTITY = r"\b(llc|l\.l\.c|inc|ltd|corp|co|company|corporation|pa|p\.a|pllc|pl|lp|llp|group|firm|associates|services|partners|holdings|enterprises|industries|trust|foundation|association|properties|development|construction|realty|homes|law|bank|church|club|center|marina|pac|committee|fund)\b\.?|&"
PAC_NAME = r"\bpac\b|political|committee|advocacy fund|solidarity fund|action fund"


def is_entity(name: str) -> bool:
    """A business listed under a person's name (sole owners do this) is still a private person to us."""
    return bool(re.search(ENTITY, (name or "").lower()))


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", name or "").strip()


def summarize(rows: list[dict]) -> dict:
    """rows: contributions for one campaign (refunds included as negative amounts)."""
    by_giver = defaultdict(float)
    sectors = defaultdict(lambda: {"amount": 0.0, "people": 0.0, "business": 0.0, "count": 0, "names": defaultdict(float)})
    committees = defaultdict(lambda: {"amount": 0.0, "kind": "other"})
    parties = defaultdict(float)
    addr = defaultdict(lambda: {"amount": 0.0, "names": set()})
    total = inkind = 0.0
    for r in rows:
        a = float(r["amount"])
        total += a
        if r.get("item") == "IK":
            inkind += a
        t = r["type"]
        if t == "B" and re.search(PAC_NAME, (r.get("name") or "").lower()):
            t = "F"  # a committee filed as a business
        if t == "B" and (not is_entity(r.get("name")) or "protected" in (r.get("addr") or "")):
            t = "O"  # a person's own name on a business gift: count it with people, by occupation
        if t == "S" or (t == "I" and r.get("self")):
            by_giver["self"] += a
            continue
        if t == "P":
            by_giver["party"] += a
            parties[_clean(r["name"])] += a
            continue
        if t in ("F", "C", "E"):
            by_giver["committee"] += a
            n = _clean(r["name"])
            committees[n]["amount"] += a
            committees[n]["kind"] = committee_kind(n)
            continue
        if t == "B":
            by_giver["business"] += a
            # The business's own stated line of work first, then its name.
            s = sector(r.get("occ", "")) or sector(r.get("name", "")) or "other-business"
            sectors[s]["business"] += a
            sectors[s]["names"][_clean(r["name"])] += a
            if r.get("addr"):
                addr[r["addr"]]["amount"] += a
                addr[r["addr"]]["names"].add(_clean(r["name"]))
        else:  # a person (I) or other (O)
            by_giver["people"] += a
            occ = (r.get("occ") or "").strip()
            s = "unstated" if not occ else "nojob" if re.search(NO_JOB, occ.lower()) else (sector(occ) or "other-job")
            sectors[s]["people"] += a
        sectors[s]["amount"] += a
        sectors[s]["count"] += 1
    out_sectors = []
    for s, v in sectors.items():
        if v["amount"] <= 0:
            continue
        top = sorted(((n, round(x)) for n, x in v["names"].items() if x > 0), key=lambda z: -z[1])[:8]
        out_sectors.append({"id": s, "label": SECTOR_LABEL[s], "amount": round(v["amount"]), "fromPeople": round(v["people"]),
                            "fromBusinesses": round(v["business"]), "gifts": v["count"], "topBusinesses": top})
    out_sectors.sort(key=lambda x: -x["amount"])
    # Several companies at one address, together giving more than one donor could. Legal, and worth seeing.
    clusters = sorted(({"names": sorted(v["names"]), "amount": round(v["amount"])} for v in addr.values()
                       if len(v["names"]) >= 3 and v["amount"] >= 3000), key=lambda c: -c["amount"])
    return {
        "total": round(total), "inKind": round(inkind),
        "byGiver": {k: round(v) for k, v in by_giver.items() if round(v)},
        "sectors": out_sectors,
        "committees": sorted(({"name": n, "amount": round(v["amount"]), "kind": v["kind"], "kindLabel": KIND_LABEL[v["kind"]]}
                              for n, v in committees.items() if v["amount"] > 0), key=lambda c: -c["amount"]),
        "parties": sorted(({"name": n, "amount": round(a)} for n, a in parties.items() if a > 0), key=lambda c: -c["amount"]),
        "sharedAddress": clusters[:6],
    }


def _match(name: str, people: list[dict]) -> dict | None:
    base = name.replace(" Jr.", "").replace(" Jr", "").replace(" II", "").strip()
    last = base.split()[-1].lower()
    first = base.split()[0].lower().strip('"')
    c = [p for p in people if p["name"].lower().replace(" jr.", "").split()[-1].strip(".,") == last]
    if len(c) > 1:
        c = [p for p in c if p["name"].lower().startswith(first)] or c
    return c[0] if len(c) == 1 else None


def merge(seed: dict, county: str) -> dict:
    f = ROOT / "data" / "contrib" / f"{county}.json"
    if not f.exists():
        return seed
    d = json.loads(f.read_text())
    seed["sources"].setdefault(SOURCE_ID, {
        "title": f"Itemized campaign contribution reports, {d.get('cycle', '2026')} election",
        "url": d.get("url") or "https://www.voterfocus.com/CampaignFinance/candidate_pr.php",
        "publisher": f"{seed['county']['name']} Supervisor of Elections" if isinstance(seed.get("county"), dict) else "County Supervisor of Elections",
        "tier": 1, "accessed": d.get("pulledAt", "")[:10]})
    for ca, c in d.get("campaigns", {}).items():
        p = _match(c["candidate"], seed["people"])
        if not p:
            continue
        s = summarize(c["rows"])
        s.update({"office": c.get("office"), "reportUrl": c.get("url"), "through": max((r["date"] for r in c["rows"] if r.get("date")), default=None),
                  "source": SOURCE_ID})
        p["funding"] = s
    return seed
